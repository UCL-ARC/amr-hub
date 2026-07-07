"""
AMR-HUB: Behavioural-cloning prototype, rebuilt against the real DuckDB schema.

WHAT CHANGED FROM THE CSV PROTOTYPE
-----------------------------------
The original prototype assumed a flat CSV with a single `zone` column and four
event types (workstation, attend_patient, door_access, occupy_content). The
actual data is relational and different in four load-bearing ways:

1. No `zone`. Location = SourceKey, and SourceKey lives in a DIFFERENT key space
   per InteractionTypeClass:
       Door Message -> Ref.Door        (13 keys)
       Roster       -> Ref.Roster      (2 keys)
       Workstation  -> Ref.Workstation (36 keys)
       Flowsheet    -> 168 keys (likely a location/department; NOT the 119
                       FlowsheetTemplates, which are keyed by InteractionTypeKey)
   Keys from different classes must never collide, but doors, workstations,
   and flowsheets DO share a physical frame -- see note 5.

2. Shifts are explicit. Roster Start / Roster End paired by LinkKey define the
   shift window. LinkKey is populated ONLY for roster events. So we window
   activity by rostered intervals instead of the old occupy_content / 8h-gap
   heuristic. TERMINAL_EVENTS and split_into_shifts are gone.

3. No scarcity. ~2.8M events across ~3,609 staff. The Markov *bootstrap* is
   retired as a data generator; Markov survives as a first-class BASELINE model.

4. New features: Role/StaffGroup (Ref.Staff), fine activity (32 InteractionType
   values), and the patient-infection link (PatientDurableKey -> PatientInfection).

5. SHARED SPATIAL FRAME (this revision). Doors, workstations, and flowsheet
   entries live in the same physical space, so a door badge, a workstation
   login, and a flowsheet entry in the same room should collapse to ONE
   location symbol ("room:<name>") rather than three namespaced ones. Class
   keys are resolved to a canonical room in priority order:
       (a) CROSSWALK_CSV   -- a hand-built (iclass, source_key, room) mapping
       (b) ROOM_RESOLUTION -- a room column joined from a spatial ref table
       (c) fallback        -- the old per-class namespaced symbol
                              ("door:...", "ws:...", "fs:...")
   What the data audit shows about (b): Ref.Door (13 rows) and
   Ref.Workstation (36 rows) carry key + name ONLY -- no spatial columns --
   so doors and workstations reach the shared frame exclusively via the
   crosswalk (49 rows to hand-map). Ref.Department (221 bed-level rows with
   Bed/Room/Location names) is the sole spatial table; the working
   hypothesis is that the 168 Flowsheet SourceKeys join to DepartmentKey,
   with RoomName as the shared symbol (confirmed by the team: the DB's
   reference table links flowsheet SourceKeys to bed location names).
   Door endpoints and RoomNames pass through one std_code(), and the
   coverage report checks their vocabularies actually overlap.
   The fallback means a partial crosswalk degrades gracefully: unmapped keys
   stay distinct instead of silently colliding or being dropped. A coverage
   report after load shows how much of each class landed in the shared frame
   and whether any room actually contains >=2 classes (the collapse check).

WHAT THIS SCRIPT DOES
---------------------
    load  -> build one shared-frame touchpoint sequence per (staff, shift)
    battery -> quantify learnability WITHOUT committing to IRL:
                 - sequence entropy + conditional entropy H(next | state)
                 - process-style variant statistics (how many distinct paths)
                 - Markov baseline: held-out top-1 / top-k / perplexity
                 - optional BC: held-out top-1 / top-k
    sweep -> the Occam state-variant comparison, now over real features.

The battery is the part that answers "is this learnable / too noisy". It runs
with numpy + duckdb alone. BC (Flax/optax) is optional and guarded.

Run (everything below needs ONLY the DuckDB file):
    python bc_prototype.py --db <your.duckdb> infer-ws          # place WOWs
    # review/edit ws_crosswalk.csv (blank rooms are skipped)
    python bc_prototype.py --db <your.duckdb> battery --crosswalk ws_crosswalk.csv
    python bc_prototype.py --db <your.duckdb> ruleout --crosswalk ws_crosswalk.csv --bc
    python bc_prototype.py --db <your.duckdb> sweep   --crosswalk ws_crosswalk.csv
Optional, when Keiran's nursing-staff sheet arrives (adds floorplan room
codes; results should barely move -- it mostly re-labels):
    ... any command ... --nursing nursing.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import duckdb
import numpy as np

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

N_TIME_BUCKETS = 4  # 0-6, 6-12, 12-18, 18-24
KEEP_UNROSTERED = False  # events outside any rostered interval
MIN_SHIFT_EVENTS = 3  # shifts shorter than this are dropped
TOPK = 3

# Class prefixes used ONLY for the fallback path, when a key cannot be
# resolved into the shared room frame. They keep unmapped keys from
# colliding across key spaces.
CLASS_PREFIX = {
    "Door Message": "door",
    "Workstation": "ws",
    "Flowsheet": "fs",
    "Roster": "roster",
}

# Which ref table each class's SourceKey resolves against for a human-readable
# FALLBACK name. Flowsheet is left unresolved by default and falls back to the
# raw key; set FLOWSHEET_SOURCE_TABLE once a join test confirms where the 168
# keys point.
SOURCE_REF = {
    "Door Message": ("Ref.Door", "DoorKey", "DoorName"),
    "Workstation": ("Ref.Workstation", "WorkstationKey", "WorkstationName"),
    "Roster": ("Ref.Roster", "RosterKey", "RosterName"),
}
FLOWSHEET_SOURCE_TABLE = None  # e.g. ("Ref.Department", "DepartmentKey", "RoomName")

# --- shared spatial frame -----------------------------------------
# Canonical namespace = the ROOM CODES used by on-ward nursing staff and the
# floorplans (per Keiran). Each class reaches it by a different route:
#
#   Flowsheet    NURSING_CSV: the nursing-staff table linking bed location
#                names ("cot X - nursery Y", held in Ref.Department against
#                DepartmentKey = SourceKey) to room codes. Authoritative.
#                The Ref.Department RoomName join below stays only as a
#                fallback tier beneath it.
#   Door Message DoorName encodes the TWO locations the door connects
#                ("A - B"). A door is an edge, not a point -- we cannot know
#                which side the staff member was on -- so doors resolve to a
#                standardised edge symbol "door:A|B" whose endpoints live in
#                the room-code vocabulary. Regex in DOOR_NAME_SEPARATORS /
#                std_code(); tune once real strings are inspected.
#   Workstation  no direct location. `infer-ws` implements Keiran's plan:
#                infer each workstation's room from co-occurring flowsheet
#                rooms (same staff, +/- a few minutes), emitting crosswalk
#                rows with support/share stats for review.
#   Roster       unit-level only (2 keys) -- far too coarse to be a location,
#                but attached to each Shift as a `unit` feature and exposed
#                to the state-variant sweep (S6).
#
# Priority per key: crosswalk CSV > nursing CSV > join below > edge parse
# (doors) > namespaced fallback. Partial coverage degrades gracefully.
ROOM_RESOLUTION: dict[str, tuple[str, str, str] | None] = {
    "Door Message": None,  # edge-parsed from DoorName instead
    "Workstation": None,  # inferred via `infer-ws` instead
    "Flowsheet": ("Ref.Department", "DepartmentKey", "RoomName"),  # fallback tier
}

# Optional pretty-name lookup for room keys: (table, key_col, name_col).
# There is no Ref.Room table in this DB; rooms arrive directly as code
# strings from the nursing table / crosswalk, so this stays None.
ROOM_NAME_TABLE: tuple[str, str, str] | None = None

# Optional hand-built crosswalk CSV with header: iclass,source_key,room
# Rows override / extend every other source. Rows with an empty room are
# skipped (lets `infer-ws` review output double as an editable template).
CROSSWALK_CSV: str | None = None

# Nursing-staff table CSV linking flowsheet locations to room codes.
# Accepted layouts (header names are matched case-insensitively):
#   source_key,room            direct: DepartmentKey -> room code
#   bed,room  (or bed_name)    bed location name -> room code; joined through
#                              Ref.Department (BedName, then RoomName) on a
#                              normalised string match to recover SourceKeys.
NURSING_CSV: str | None = None

# Door-name edge parsing: DoorName = "<loc A> <sep> <loc B>".
DOOR_EDGES = True
DOOR_NAME_SEPARATORS = r"\s+(?:-|\u2013|\u2014|<->|/|to)\s+"


def std_code(s: str) -> str:
    """Standardise a location/room code string. Extend with the regex clean-up
    Keiran anticipates once real DoorName strings have been inspected."""
    return re.sub(r"\s+", " ", s.strip()).upper()


# infer-ws parameters: a workstation is assigned the modal flowsheet room
# charted by the same staff member within +/- WS_WINDOW_MIN minutes, if that
# room wins >= WS_MIN_SHARE of votes over >= WS_MIN_SUPPORT co-occurrences.
WS_WINDOW_MIN = 10
WS_MIN_SUPPORT = 20
WS_MIN_SHARE = 0.6


# ------------------------------------------------------------------
# 1. Load: relational -> shared-frame touchpoint sequences
# ------------------------------------------------------------------


@dataclass
class Step:
    ts: float  # epoch seconds
    location: str  # canonical "room:<code>" / "door:A|B" (or fallback "ws:...")
    iclass: str  # InteractionTypeClass
    itype: str  # InteractionType (fine)
    role: str
    patient: str | None
    time_bucket: int
    unit: str = "unknown"  # rostered unit (Ref.Roster), shift-level


@dataclass
class Shift:
    staff: str
    link_key: int
    unit: str = "unknown"
    steps: list[Step] = field(default_factory=list)


def _load_ref_map(con, table, key_col, name_col) -> dict[int, str]:
    rows = con.execute(f"select {key_col}, {name_col} from {table}").fetchall()
    return {int(k): str(v) for k, v in rows if k is not None}


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _load_nursing_map(con, nursing_csv: str) -> dict[int, str]:
    """Nursing-staff table -> {Flowsheet SourceKey: 'room:<code>'}.

    Direct layout (source_key column) is used as-is. Bed-name layout is
    joined through Ref.Department on a normalised match against BedName,
    then RoomName, to recover DepartmentKey (= SourceKey)."""
    with open(nursing_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
        rows = list(reader)

    def col(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    key_c = col("source_key", "sourcekey", "key", "departmentkey")
    bed_c = col("bed", "bed_name", "bedname", "bed_location", "location")
    room_c = col("room", "room_code", "roomcode")
    if room_c is None or (key_c is None and bed_c is None):
        raise SystemExit(
            f"[nursing] {nursing_csv}: need a room column plus either a "
            f"source_key or bed-name column; found {list(cols)}"
        )

    out: dict[int, str] = {}
    if key_c is not None:
        for r in rows:
            if r[key_c] and r[room_c] and r[room_c].strip():
                out[int(r[key_c])] = f"room:{std_code(r[room_c])}"
        print(f"[nursing] {len(out)} flowsheet keys mapped directly.")
        return out

    dep = con.execute(
        "select DepartmentKey, BedName, RoomName from Ref.Department"
    ).fetchall()
    by_bed: dict[str, list[int]] = defaultdict(list)
    by_room: dict[str, list[int]] = defaultdict(list)
    for k, b, rn in dep:
        if k is None:
            continue
        if b:
            by_bed[_norm_name(b)].append(int(k))
        if rn:
            by_room[_norm_name(rn)].append(int(k))

    unmatched = []
    for r in rows:
        bed, room = r.get(bed_c, ""), r.get(room_c, "")
        if not bed or not room or not room.strip():
            continue
        keys = by_bed.get(_norm_name(bed)) or by_room.get(_norm_name(bed))
        if not keys:
            unmatched.append(bed)
            continue
        for k in keys:
            out[k] = f"room:{std_code(room)}"
    print(
        f"[nursing] {len(out)} flowsheet keys mapped via bed names; "
        f"{len(unmatched)} nursing rows unmatched"
        + (f" (e.g. {unmatched[:3]!r})" if unmatched else "")
        + "."
    )
    return out


def _parse_door_edges(door_names: dict[int, str]) -> dict[int, str]:
    """DoorName 'A <sep> B' -> {DoorKey: 'door:A|B'} with standardised,
    order-independent endpoints. Names that do not split into exactly two
    parts are left out (they fall back to the raw namespaced name)."""
    out: dict[int, str] = {}
    for k, name in door_names.items():
        parts = [std_code(p) for p in re.split(DOOR_NAME_SEPARATORS, name) if p.strip()]
        if len(parts) == 2:
            a, b = sorted(parts)
            out[k] = f"door:{a}|{b}"
    return out


def _load_room_maps(
    con, crosswalk_csv: str | None, nursing_csv: str | None = None
) -> dict[str, dict[int, str]]:
    """Per-class {source_key -> canonical symbol}: 'room:<code>' for points,
    'door:A|B' for door edges.

    Priority (later overrides earlier): ROOM_RESOLUTION joins -> door edge
    parse -> nursing CSV -> crosswalk CSV. Any class with no mapping at all
    is absent from the dict and uses the namespaced fallback."""
    # Optional room-key -> room-name prettifier, shared across classes.
    room_names: dict[int, str] = {}
    if ROOM_NAME_TABLE is not None:
        try:
            room_names = _load_ref_map(con, *ROOM_NAME_TABLE)
        except duckdb.Error:
            print(
                f"[rooms] {ROOM_NAME_TABLE[0]} not readable; using raw room keys as symbols."
            )

    def room_symbol(room_val) -> str:
        try:
            k = int(room_val)
            name = room_names.get(k)
            return f"room:{std_code(name)}" if name is not None else f"room:{k}"
        except (TypeError, ValueError):
            # String room names go through the SAME standardisation as door
            # endpoints, so "Nursery 1" (RoomName) and "nursery 1" (in a
            # DoorName) land on one spelling and the frames can align.
            return f"room:{std_code(str(room_val))}"

    maps: dict[str, dict[int, str]] = {}
    for iclass, spec in ROOM_RESOLUTION.items():
        if spec is None:
            continue
        tbl, kcol, rcol = spec
        try:
            rows = con.execute(f"select {kcol}, {rcol} from {tbl}").fetchall()
        except duckdb.Error as e:
            print(
                f"[rooms] {iclass}: cannot read {rcol} from {tbl} "
                f"({type(e).__name__}); leaving this class on the namespaced fallback."
            )
            continue
        maps[iclass] = {
            int(k): room_symbol(r) for k, r in rows if k is not None and r is not None
        }

    if DOOR_EDGES:
        try:
            door_names = _load_ref_map(con, *SOURCE_REF["Door Message"])
            edges = _parse_door_edges(door_names)
            maps.setdefault("Door Message", {}).update(edges)
            print(
                f"[rooms] door edges parsed: {len(edges)}/{len(door_names)} "
                "door names split into two endpoints."
            )
        except duckdb.Error:
            pass

    if nursing_csv:
        maps.setdefault("Flowsheet", {}).update(_load_nursing_map(con, nursing_csv))

    if crosswalk_csv:
        n_rows = n_skip = 0
        with open(crosswalk_csv, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                room = (row.get("room") or "").strip()
                if not room:
                    n_skip += 1
                    continue
                iclass = row["iclass"].strip()
                key = int(row["source_key"])
                maps.setdefault(iclass, {})[key] = f"room:{std_code(room)}"
                n_rows += 1
        print(
            f"[rooms] crosswalk {crosswalk_csv}: {n_rows} mappings applied"
            + (f", {n_skip} blank rows skipped" if n_skip else "")
            + "."
        )

    return maps


def load_shifts(
    con, crosswalk_csv: str | None = None, nursing_csv: str | None = None
) -> tuple[list[Shift], Counter]:
    """Build per-(staff, shift) touchpoint sequences from DuckDB.

    Returns (shifts, resolution_stats) where resolution_stats counts, per
    (iclass, outcome), how each event's location was resolved:
    outcome in {"room", "edge", "fallback", "null"}.
    """
    # Fallback name maps (old behaviour) and the shared room maps.
    loc_maps: dict[str, dict[int, str]] = {}
    for iclass, (tbl, kcol, ncol) in SOURCE_REF.items():
        loc_maps[iclass] = _load_ref_map(con, tbl, kcol, ncol)
    if FLOWSHEET_SOURCE_TABLE:
        tbl, kcol, ncol = FLOWSHEET_SOURCE_TABLE
        loc_maps["Flowsheet"] = _load_ref_map(con, tbl, kcol, ncol)

    room_maps = _load_room_maps(con, crosswalk_csv, nursing_csv)
    roster_names = loc_maps.get("Roster", {})
    res_stats: Counter = Counter()

    def resolve(iclass: str, source_key) -> str:
        prefix = CLASS_PREFIX.get(iclass, "x")
        if source_key is None:
            res_stats[(iclass, "null")] += 1
            return f"{prefix}:na"
        k = int(source_key)
        # 1) shared spatial frame (point rooms and door edges)
        sym = room_maps.get(iclass, {}).get(k)
        if sym is not None:
            res_stats[(iclass, "room" if sym.startswith("room:") else "edge")] += 1
            return sym
        # 2) namespaced fallback (never collides across classes)
        res_stats[(iclass, "fallback")] += 1
        name = loc_maps.get(iclass, {}).get(k)
        return f"{prefix}:{name if name is not None else source_key}"

    # One ordered stream per staff member, with everything resolved in SQL
    # except location (done in Python because it is class-conditional).
    q = """
    select
        e.MasterIndexId          as staff,
        epoch(e.EventDateTime)   as ts,
        e.SourceKey              as source_key,
        e.LinkKey                as link_key,
        e.PatientDurableKey      as patient,
        it.InteractionType       as itype,
        it.InteractionTypeClass  as iclass,
        coalesce(s.Role, 'unknown')       as role
    from Data.StaffLocationEvent e
    join Ref.InteractionType it
      on e.InteractionTypeKey = it.InteractionTypeKey
    left join Ref.Staff s
      on s.MasterIndexId = e.MasterIndexId
    order by e.MasterIndexId, e.EventDateTime
    """
    rows = con.execute(q).fetchall()

    # (a) collect rostered intervals per staff from Roster Start/End by LinkKey
    #     Roster Start's SourceKey names the unit (Ref.Roster) -- a shift-level
    #     feature, far too coarse to be a location.
    starts: dict[tuple[str, int], tuple[float, str]] = {}
    ends: dict[tuple[str, int], float] = {}
    for staff, ts, sk, link_key, patient, itype, iclass, role in rows:
        if iclass != "Roster" or link_key is None:
            continue
        key = (staff, int(link_key))
        if itype == "Roster Start":
            unit = roster_names.get(int(sk), str(sk)) if sk is not None else "unknown"
            starts[key] = (float(ts), unit)
        elif itype == "Roster End":
            ends[key] = float(ts)

    intervals: dict[str, list[tuple[float, float, int, str]]] = defaultdict(list)
    for key, (t0, unit) in starts.items():
        t1 = ends.get(key)
        if t1 is None or t1 <= t0:
            continue  # unmatched or non-monotonic pair -> skip (report separately)
        staff, link_key = key
        intervals[staff].append((t0, t1, link_key, unit))
    for staff in intervals:
        intervals[staff].sort()

    def which_shift(staff: str, ts: float) -> tuple[int, str] | None:
        for t0, t1, link_key, unit in intervals.get(
            staff, ()
        ):  # linear; fine for a prototype
            if t0 <= ts <= t1:
                return link_key, unit
        return None

    # (b) assign each activity event to its containing shift
    shifts: dict[tuple[str, int], Shift] = {}
    for staff, ts, sk, link_key, patient, itype, iclass, role in rows:
        if iclass == "Roster":
            continue
        ts = float(ts)
        hit = which_shift(staff, ts)
        if hit is None:
            if not KEEP_UNROSTERED:
                continue
            sh, unit = -1, "unknown"
        else:
            sh, unit = hit
        skey = (staff, sh)
        if skey not in shifts:
            shifts[skey] = Shift(staff=staff, link_key=sh, unit=unit)
        tb = min(N_TIME_BUCKETS - 1, int(((ts % 86400) / 86400) * N_TIME_BUCKETS))
        shifts[skey].steps.append(
            Step(
                ts=ts,
                location=resolve(iclass, sk),
                iclass=iclass,
                itype=itype,
                role=str(role),
                patient=(str(patient) if patient is not None else None),
                time_bucket=tb,
                unit=unit,
            )
        )

    kept = [shift for shift in shifts.values() if len(shift.steps) >= MIN_SHIFT_EVENTS]
    for shift in kept:
        shift.steps.sort(key=lambda st: st.ts)
    return kept, res_stats


def report_spatial_frame(shifts: list[Shift], res_stats: Counter) -> None:
    """Coverage of the shared room frame + the actual collapse check.

    Two failure modes this catches:
      - low room coverage: ROOM_RESOLUTION columns wrong / crosswalk too thin,
        so most events are still living in per-class namespaces;
      - zero multi-class rooms: every class resolved, but into DISJOINT room
        sets -- i.e. the room columns do not share a key space and nothing
        actually collapsed. Symbols would look canonical while behaving
        exactly like the old namespaced ones.
    """
    print("\n--- shared spatial frame ---")
    for iclass in sorted({c for c, _ in res_stats}):
        room = res_stats.get((iclass, "room"), 0)
        edge = res_stats.get((iclass, "edge"), 0)
        fb = res_stats.get((iclass, "fallback"), 0)
        nul = res_stats.get((iclass, "null"), 0)
        tot = max(1, room + edge + fb + nul)
        print(
            f"  {iclass:14s} room {room / tot:6.1%}   edge {edge / tot:6.1%}   "
            f"fallback {fb / tot:6.1%}   null {nul / tot:6.1%}   ({tot} events)"
        )

    room_classes: dict[str, set[str]] = defaultdict(set)
    endpoints: set[str] = set()
    for sh in shifts:
        for s in sh.steps:
            if s.location.startswith("room:"):
                room_classes[s.location].add(s.iclass)
            elif s.location.startswith("door:") and "|" in s.location:
                endpoints.update(s.location[len("door:") :].split("|"))
    multi = sum(1 for v in room_classes.values() if len(v) >= 2)
    print(
        f"  rooms in shared frame: {len(room_classes)}; containing >=2 classes: {multi}"
    )
    room_capable = {c for (c, outcome) in res_stats if outcome == "room"}
    if len(room_capable) >= 2 and multi == 0:
        print(
            "  WARNING: >=2 classes resolve to rooms, yet no room contains "
            "more than one class -- their room vocabularies are disjoint; "
            "nothing has collapsed. Check spellings / the crosswalk."
        )
    elif len(room_capable) < 2 and room_classes:
        print(
            "  (collapse check idle: only one class resolves to point-rooms "
            "so far -- expected until infer-ws output is applied.)"
        )

    # Door-endpoint vocabulary vs room-code vocabulary. Endpoints naming
    # corridors, kitchens, stairwells legitimately never match; but if NO
    # endpoint matches any room, the two vocabularies use different spellings
    # for the same places -> extend std_code() with the needed regex.
    if endpoints:
        rooms = {r[len("room:") :] for r in room_classes}
        matched = sorted(endpoints & rooms)
        unmatched = sorted(endpoints - rooms)
        print(
            f"  door endpoints: {len(endpoints)} distinct; "
            f"{len(matched)} match a room code"
            + (f" (e.g. {matched[:3]})" if matched else "")
            + "."
        )
        if unmatched:
            print(f"  endpoints with no matching room: {unmatched}")
        if not matched:
            print(
                "  NOTE: zero endpoint/room matches -- likely a spelling "
                "mismatch between DoorName parts and RoomName; inspect the "
                "lists above and extend std_code()."
            )


# ------------------------------------------------------------------
# 1c. infer-ws: place workstations by co-occurrence with flowsheet rooms
# ------------------------------------------------------------------


def run_infer_ws(
    con,
    nursing_csv: str | None,
    out_path: str,
    window_min: int = WS_WINDOW_MIN,
    min_support: int = WS_MIN_SUPPORT,
    min_share: float = WS_MIN_SHARE,
) -> None:
    """Keiran's plan (b): infer each workstation's room from where the SAME
    staff member charts flowsheets within +/- `window_min` minutes of using
    it. The modal room wins if it has enough votes (support) and a clear
    enough majority (share). Confident rows get a room; the rest are written
    with a blank room (the crosswalk loader skips blanks, so the output file
    is directly usable AND directly editable).

    Caveat: WOWs are mobile. A workstation with a split vote may genuinely
    have no fixed room; treat share as a fixedness score, not only as
    matching confidence."""
    room_maps = _load_room_maps(con, None, nursing_csv)
    fs_rooms = room_maps.get("Flowsheet", {})
    if not fs_rooms:
        raise SystemExit(
            "[infer-ws] no flowsheet room mapping available; "
            "provide --nursing or fix ROOM_RESOLUTION first."
        )
    ws_names = _load_ref_map(con, *SOURCE_REF["Workstation"])

    rows = con.execute("""
        select e.MasterIndexId, epoch(e.EventDateTime), e.SourceKey,
               it.InteractionTypeClass
        from Data.StaffLocationEvent e
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        where it.InteractionTypeClass in ('Workstation', 'Flowsheet')
          and e.SourceKey is not null
        order by e.MasterIndexId, e.EventDateTime
    """).fetchall()

    window = window_min * 60.0
    votes: dict[int, Counter] = defaultdict(Counter)
    from itertools import groupby

    # Per staff member: two-pointer sweep of flowsheet events around each
    # workstation event.
    for _staff, grp in groupby(rows, key=lambda r: r[0]):
        evs = [(float(ts), int(sk), ic) for _s, ts, sk, ic in grp]
        fs = [
            (ts, fs_rooms[sk])
            for ts, sk, ic in evs
            if ic == "Flowsheet" and sk in fs_rooms
        ]
        if not fs:
            continue
        lo = 0
        for ts, sk, ic in evs:
            if ic != "Workstation":
                continue
            while lo < len(fs) and fs[lo][0] < ts - window:
                lo += 1
            j = lo
            while j < len(fs) and fs[j][0] <= ts + window:
                votes[sk][fs[j][1]] += 1
                j += 1

    n_conf = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "iclass",
                "source_key",
                "name_hint",
                "room",
                "support",
                "share",
                "runner_up",
            ]
        )
        for sk in sorted(ws_names):
            ctr = votes.get(sk, Counter())
            support = sum(ctr.values())
            if support == 0:
                w.writerow(["Workstation", sk, ws_names[sk], "", 0, "", ""])
                continue
            ranked = ctr.most_common(2)
            best_room, best_n = ranked[0]
            runner = ranked[1][0].removeprefix("room:") if len(ranked) > 1 else ""
            share = best_n / support
            confident = support >= min_support and share >= min_share
            room = best_room.removeprefix("room:") if confident else ""
            if confident:
                n_conf += 1
            w.writerow(
                ["Workstation", sk, ws_names[sk], room, support, f"{share:.2f}", runner]
            )
    print(
        f"[infer-ws] {n_conf}/{len(ws_names)} workstations placed "
        f"(window=+/-{window_min}min, support>={min_support}, share>={min_share})."
    )
    print(
        f"[infer-ws] wrote {out_path}; low-share rows left blank -- a WOW "
        "with a split vote may genuinely be mobile, not just uncertain. "
        "Review, edit, then pass via --crosswalk."
    )


# ------------------------------------------------------------------
# 2. State / action variants (what BC and Markov condition on)
# ------------------------------------------------------------------
# Action target = next location by default (the movement question). Swap to
# "iclass" or "itype" to ask "what do they do next" instead. Note that with
# the shared frame, "next_loc" now genuinely means "next room" for resolved
# events; iclass survives separately in S4, so no information is destroyed
# by the collapse -- it just moves out of the location symbol.

STATE_VARIANTS = {
    "S1_loc": lambda s, prev: (s.location,),
    "S2_loc_time": lambda s, prev: (s.location, s.time_bucket),
    "S3_loc_time_role": lambda s, prev: (s.location, s.time_bucket, s.role),
    "S4_loc_time_role_class": lambda s, prev: (
        s.location,
        s.time_bucket,
        s.role,
        s.iclass,
    ),
    "S5_bigram": lambda s, prev: (
        s.location,
        s.time_bucket,
        s.role,
        (prev.location if prev else "<s>"),
    ),
    "S6_bigram_unit": lambda s, prev: (
        s.location,
        s.time_bucket,
        s.role,
        (prev.location if prev else "<s>"),
        s.unit,
    ),
}
ACTION_KEYS = {
    "next_loc": lambda s: s.location,
    "next_class": lambda s: s.iclass,
    "next_itype": lambda s: s.itype,
}


def build_pairs(shifts, state_fn, action_key):
    """Return list of (state_tuple, action_str) across all shifts."""
    pairs = []
    for sh in shifts:
        prev = None
        for cur, nxt in zip(sh.steps, sh.steps[1:]):
            pairs.append((state_fn(cur, prev), action_key(nxt)))
            prev = cur
    return pairs


def split_pairs(pairs, frac=0.8, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(pairs))
    cut = int(len(pairs) * frac)
    tr = [pairs[i] for i in idx[:cut]]
    te = [pairs[i] for i in idx[cut:]]
    return tr, te


# ------------------------------------------------------------------
# 3. Learnability battery
# ------------------------------------------------------------------


def conditional_entropy(pairs) -> tuple[float, float]:
    """H(action) and H(action | state), in bits. Gap = mutual information."""
    a_counts = Counter(a for _, a in pairs)
    n = sum(a_counts.values())
    H_a = -sum((c / n) * math.log2(c / n) for c in a_counts.values())

    by_state: defaultdict[tuple, Counter] = defaultdict(Counter)
    for s, a in pairs:
        by_state[s][a] += 1
    H_a_given_s = 0.0
    for s, ctr in by_state.items():
        m = sum(ctr.values())
        h = -sum((c / m) * math.log2(c / m) for c in ctr.values())
        H_a_given_s += (m / n) * h
    return H_a, H_a_given_s


def variant_stats(shifts, action_key) -> dict:
    """Process-mining-style: how many distinct action paths, how concentrated."""
    paths = Counter(tuple(action_key(s) for s in sh.steps) for sh in shifts)
    total = sum(paths.values())
    top = paths.most_common(1)[0][1] if paths else 0
    return {
        "n_shifts": len(shifts),
        "distinct_paths": len(paths),
        "top_path_share": round(top / total, 3) if total else 0.0,
        "singletons": sum(1 for c in paths.values() if c == 1),
    }


class MarkovModel:
    """Order-k categorical model P(action | last-k actions), Laplace-smoothed.

    This is a first-class interpretable baseline (a transition table). Its
    held-out top-k and perplexity are the primary learnability numbers.
    """

    def __init__(self, order=1, alpha=0.5):
        self.order = order
        self.alpha = alpha
        self.table: dict[tuple, Counter] = defaultdict(Counter)
        self.vocab: set = set()

    def fit(self, seq_pairs):
        # seq_pairs: list of (context_tuple, action). We only use the last-k
        # actions from context, which we encode as the state tuple here.
        for ctx, a in seq_pairs:
            self.table[ctx][a] += 1
            self.vocab.add(a)

    def _dist(self, ctx) -> dict:
        ctr = self.table.get(ctx, Counter())
        V = max(1, len(self.vocab))
        denom = sum(ctr.values()) + self.alpha * V
        return {a: (ctr.get(a, 0) + self.alpha) / denom for a in self.vocab}

    def evaluate(self, seq_pairs, topk=TOPK):
        top1 = topk_hit = 0
        ll = 0.0
        for ctx, a in seq_pairs:
            dist = self._dist(ctx)
            ranked = sorted(dist, key=dist.get, reverse=True)
            if ranked and ranked[0] == a:
                top1 += 1
            if a in ranked[:topk]:
                topk_hit += 1
            p = dist.get(a, self.alpha / max(1, len(self.vocab)))
            ll += math.log2(max(p, 1e-12))
        n = max(1, len(seq_pairs))
        return {
            "top1": round(top1 / n, 3),
            f"top{topk}": round(topk_hit / n, 3),
            "perplexity": round(2 ** (-ll / n), 2),
        }


def run_battery(shifts, action_name="next_loc", order=1):
    action_key = ACTION_KEYS[action_name]
    print(f"\n=== Learnability battery (action = {action_name}) ===")
    print("variants:", variant_stats(shifts, action_key))

    # Markov context = last `order` actions.
    seq = []
    for sh in shifts:
        acts = [action_key(s) for s in sh.steps]
        for i in range(order, len(acts)):
            ctx = tuple(acts[i - order : i])
            seq.append((ctx, acts[i]))
    tr, te = split_pairs(seq)
    m = MarkovModel(order=order)
    m.fit(tr)
    print(f"markov(order={order}) held-out:", m.evaluate(te))

    # Information-theoretic ceiling using the richest state variant.
    pairs = build_pairs(shifts, STATE_VARIANTS["S5_bigram"], action_key)
    H_a, H_ags = conditional_entropy(pairs)
    print(
        f"entropy: H(a)={H_a:.2f} bits  H(a|state)={H_ags:.2f} bits  "
        f"info gain={H_a - H_ags:.2f} bits"
    )
    print(
        "reading: large info gain + low perplexity => structure IRL can use; "
        "H(a|state) near H(a) => little conditional signal (noisy)."
    )


# ------------------------------------------------------------------
# 3b. BC rule-out: grouped split + baselines + decision rule
# ------------------------------------------------------------------
# A rule-out is only trustworthy if (a) train and test never share a shift
# (otherwise within-shift autocorrelation leaks and inflates top-1), and
# (b) BC is measured as LIFT over baselines on the SAME held-out set. On
# categorical state the empirical conditional P(a|state) is BC's ceiling; a
# neural net can only help by generalising to state combos unseen in train.


def grouped_split(shifts, frac=0.8, seed=0):
    """Split by SHIFT, not by pair. All pairs from a shift stay on one side."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(shifts))
    cut = int(len(shifts) * frac)
    return [shifts[i] for i in idx[:cut]], [shifts[i] for i in idx[cut:]]


def _topk_eval(predict, test_pairs, topk=TOPK):
    """predict: state_tuple -> ranked list of actions (best first)."""
    top1 = topk_hit = 0
    for s, a in test_pairs:
        ranked = predict(s)
        if ranked and ranked[0] == a:
            top1 += 1
        if a in ranked[:topk]:
            topk_hit += 1
    n = max(1, len(test_pairs))
    return round(top1 / n, 3), round(topk_hit / n, 3)


def run_ruleout(shifts, action_name="next_loc", use_bc=True):
    action_key = ACTION_KEYS[action_name]
    tr_shifts, te_shifts = grouped_split(shifts)
    print(f"\n=== BC rule-out (action = {action_name}) ===")
    print(f"grouped split: {len(tr_shifts)} train shifts, {len(te_shifts)} test shifts")

    # --- baseline 1: majority class (ignores state entirely) ---
    tr_actions = [action_key(s) for sh in tr_shifts for s in sh.steps]
    marginal_rank = [a for a, _ in Counter(tr_actions).most_common()]
    test_min = build_pairs(te_shifts, STATE_VARIANTS["S1_loc"], action_key)
    maj_top1, maj_topk = _topk_eval(lambda s: marginal_rank, test_min)
    print(f"{'majority-class':22s} top1={maj_top1:.3f} top{TOPK}={maj_topk:.3f}")

    # --- baseline 2: order-1 Markov P(next | current location) ---
    markov_table = defaultdict(Counter)
    for sh in tr_shifts:
        acts = [action_key(s) for s in sh.steps]
        for prev, nxt in zip(acts, acts[1:]):
            markov_table[(prev,)][nxt] += 1

    def markov_pred(_state, _cache={}):
        # state for S1 is (location,), which equals the current action symbol
        ctx = (_state[0],)
        ctr = markov_table.get(ctx)
        return [a for a, _ in ctr.most_common()] if ctr else marginal_rank

    mk_top1, mk_topk = _topk_eval(markov_pred, test_min)
    print(f"{'markov(prev-loc)':22s} top1={mk_top1:.3f} top{TOPK}={mk_topk:.3f}")

    # --- count-based BC (the ceiling for each categorical state variant) ---
    print("\ncount-based BC  P(a|state)  (unseen state -> backoff to majority):")
    count_scores = {}
    unseen_frac = {}
    for name, state_fn in STATE_VARIANTS.items():
        table = defaultdict(Counter)
        for s, a in build_pairs(tr_shifts, state_fn, action_key):
            table[s][a] += 1
        test_pairs = build_pairs(te_shifts, state_fn, action_key)
        n_unseen = sum(1 for s, _ in test_pairs if s not in table)
        unseen_frac[name] = round(n_unseen / max(1, len(test_pairs)), 3)

        def pred(s, _t=table):
            ctr = _t.get(s)
            return [a for a, _ in ctr.most_common()] if ctr else marginal_rank

        t1, tk = _topk_eval(pred, test_pairs)
        count_scores[name] = t1
        print(
            f"  {name:26s} top1={t1:.3f} top{TOPK}={tk:.3f}  "
            f"(unseen states: {unseen_frac[name]:.0%})"
        )

    # --- optional neural BC on richest state (only helps via generalisation) ---
    nn_top1 = None
    if use_bc:
        try:
            nn_top1 = _run_bc_grouped(tr_shifts, te_shifts, action_key)
            print(f"\nneural BC (S5, embeddings) top1={nn_top1:.3f}")
        except ImportError:
            print("\n[bc] flax/optax not installed; skipping neural BC.")

    # --- decision ---
    best_count = max(count_scores.values())
    best_state = max(count_scores, key=count_scores.get)
    lift_over_markov = best_count - mk_top1
    lift_over_majority = best_count - maj_top1
    print("\n--- verdict ---")
    print(f"best count-BC state: {best_state}  top1={best_count:.3f}")
    print(
        f"lift over majority: {lift_over_majority:+.3f}   "
        f"lift over markov: {lift_over_markov:+.3f}"
    )
    if lift_over_majority < 0.03:
        print(
            "RULE OUT: BC barely beats predicting the single most common action. "
            "State carries almost no signal for this target -> IRL over these "
            "features will not work either. Try a different action target, or "
            "fall to process mining / empirical-distribution ABM."
        )
    elif lift_over_markov < 0.02:
        print(
            "PARTIAL: BC beats majority but not order-1 Markov. There IS "
            "sequential structure, but the extra features (time/role/bigram) "
            "add nothing over 'where they just were'. IRL over those features "
            "is not justified; a Markov/empirical model is the honest ceiling."
        )
    else:
        if nn_top1 is not None and nn_top1 - best_count > 0.02:
            print(
                "KEEP: neural BC beats the count table -> many test state combos "
                "are unseen in train (state is sparse); embeddings generalise. "
                "BC works; carry this state into IRL."
            )
        else:
            print(
                "KEEP: BC beats both baselines and the count table is the ceiling "
                "(state is dense enough). Representation carries signal -> "
                "proceed to IRL. A count/Markov policy is a strong Mesa baseline."
            )


def _run_bc_grouped(tr_shifts, te_shifts, action_key):
    """Neural BC with a grouped split (no shift shared across train/test)."""
    import jax
    import jax.numpy as jnp
    import optax
    from flax import linen as nn

    tr = build_pairs(tr_shifts, STATE_VARIANTS["S5_bigram"], action_key)
    te = build_pairs(te_shifts, STATE_VARIANTS["S5_bigram"], action_key)
    n_fields = len(tr[0][0])
    # Build vocab from TRAIN only; map unseen test values to a reserved index.
    vocabs = []
    for f in range(n_fields):
        vals = sorted({p[0][f] for p in tr}, key=str)
        vocabs.append({v: i for i, v in enumerate(vals)})  # unseen -> len(vocab)
    a_vals = sorted({a for _, a in tr}, key=str)
    a_vocab = {v: i for i, v in enumerate(a_vals)}

    def enc_x(pairs):
        return np.array(
            [
                [vocabs[f].get(p[0][f], len(vocabs[f])) for f in range(n_fields)]
                for p in pairs
            ]
        )

    Xtr, Xte = enc_x(tr), enc_x(te)
    ytr = np.array([a_vocab[a] for _, a in tr])
    # test actions unseen in train are unpredictable by construction -> keep,
    # they simply count as misses (honest for a rule-out).
    yte = np.array([a_vocab.get(a, -1) for _, a in te])

    class BC(nn.Module):
        sizes: tuple
        n_out: int

        @nn.compact
        def __call__(self, x):
            embs = [
                nn.Embed(self.sizes[f] + 1, 8)(x[:, f]) for f in range(len(self.sizes))
            ]
            h = jnp.concatenate(embs, axis=-1)
            h = nn.relu(nn.Dense(64)(h))
            return nn.Dense(self.n_out)(h)

    model = BC(tuple(len(v) for v in vocabs), len(a_vocab))
    params = model.init(jax.random.PRNGKey(0), jnp.array(Xtr[:2]))
    opt = optax.adam(1e-2)
    opt_state = opt.init(params)

    def loss_fn(p, xb, yb):
        logits = model.apply(p, xb)
        return optax.softmax_cross_entropy_with_integer_labels(logits, yb).mean()

    @jax.jit
    def step(p, os, xb, yb):
        loss, g = jax.value_and_grad(loss_fn)(p, xb, yb)
        u, os = opt.update(g, os)
        return optax.apply_updates(p, u), os, loss

    Xtrj, ytrj = jnp.array(Xtr), jnp.array(ytr)
    for _ in range(300):
        params, opt_state, _ = step(params, opt_state, Xtrj, ytrj)
    pred = np.array(model.apply(params, jnp.array(Xte)).argmax(-1))
    return float((pred == yte).mean())


# ------------------------------------------------------------------
# 4. Occam state-variant sweep (Markov as the fast learner)
# ------------------------------------------------------------------


def run_sweep(shifts, action_name="next_loc", use_bc=False):
    action_key = ACTION_KEYS[action_name]
    print(f"\n=== State-variant sweep (action = {action_name}) ===")
    print(f"{'variant':28s} {'top1':>6s} {'top3':>6s}")
    prev_top1 = None
    for name, state_fn in STATE_VARIANTS.items():
        pairs = build_pairs(shifts, state_fn, action_key)
        tr, te = split_pairs(pairs)
        # Reuse MarkovModel as a generic P(a|state) lookup over the full state.
        m = MarkovModel(order=0)
        m.fit(tr)
        r = m.evaluate(te)
        gain = "" if prev_top1 is None else f"  ({r['top1'] - prev_top1:+.3f})"
        print(f"{name:28s} {r['top1']:6.3f} {r[f'top{TOPK}']:6.3f}{gain}")
        prev_top1 = r["top1"]
    if use_bc:
        try:
            _run_bc(shifts, action_key)
        except ImportError:
            print("\n[bc] flax/optax not installed; skipping neural BC.")


def _run_bc(shifts, action_key):
    """Optional Flax MLP BC over the richest state. Guarded import."""
    import jax
    import jax.numpy as jnp
    import optax
    from flax import linen as nn

    pairs = build_pairs(shifts, STATE_VARIANTS["S5_bigram"], action_key)
    # Encode each categorical field with its own vocab.
    n_fields = len(pairs[0][0])
    vocabs = [
        {v: i for i, v in enumerate({p[0][f] for p in pairs})} for f in range(n_fields)
    ]
    a_vocab = {v: i for i, v in enumerate({a for _, a in pairs})}
    X = np.array([[vocabs[f][p[0][f]] for f in range(n_fields)] for p in pairs])
    y = np.array([a_vocab[a] for _, a in pairs])
    tr, te = split_pairs(list(range(len(y))))
    tr, te = np.array(tr), np.array(te)

    class BC(nn.Module):
        sizes: tuple
        n_out: int

        @nn.compact
        def __call__(self, x):
            embs = [nn.Embed(self.sizes[f], 8)(x[:, f]) for f in range(len(self.sizes))]
            h = jnp.concatenate(embs, axis=-1)
            h = nn.relu(nn.Dense(64)(h))
            return nn.Dense(self.n_out)(h)

    model = BC(tuple(len(v) for v in vocabs), len(a_vocab))
    key = jax.random.PRNGKey(0)
    params = model.init(key, jnp.array(X[:2]))
    opt = optax.adam(1e-2)
    opt_state = opt.init(params)

    def loss_fn(p, xb, yb):
        logits = model.apply(p, xb)
        return optax.softmax_cross_entropy_with_integer_labels(logits, yb).mean()

    @jax.jit
    def step(p, os, xb, yb):
        loss, g = jax.value_and_grad(loss_fn)(p, xb, yb)
        u, os = opt.update(g, os)
        return optax.apply_updates(p, u), os, loss

    Xtr, ytr = jnp.array(X[tr]), jnp.array(y[tr])
    for _ in range(300):
        params, opt_state, _ = step(params, opt_state, Xtr, ytr)
    logits = model.apply(params, jnp.array(X[te]))
    pred = np.array(logits.argmax(-1))
    top1 = float((pred == y[te]).mean())
    print(f"\n[bc] S5_bigram held-out top1 = {top1:.3f}")


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to the DuckDB file")
    ap.add_argument("cmd", choices=["infer-ws", "battery", "sweep", "ruleout"])
    ap.add_argument("--action", default="next_loc", choices=list(ACTION_KEYS))
    ap.add_argument("--order", type=int, default=1)
    ap.add_argument("--bc", action="store_true")
    ap.add_argument(
        "--crosswalk",
        default=CROSSWALK_CSV,
        help="CSV with columns iclass,source_key,room mapping "
        "class-specific keys into the shared room frame",
    )
    ap.add_argument(
        "--nursing",
        default=NURSING_CSV,
        help="optional nursing-staff CSV linking flowsheet bed "
        "locations (or SourceKeys) to floorplan room codes",
    )
    ap.add_argument(
        "--out", default="ws_crosswalk.csv", help="(infer-ws only) output CSV path"
    )
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)

    if args.cmd == "infer-ws":
        run_infer_ws(con, nursing_csv=args.nursing, out_path=args.out)
        return
    shifts, res_stats = load_shifts(
        con, crosswalk_csv=args.crosswalk, nursing_csv=args.nursing
    )
    print(
        f"loaded {len(shifts)} shifts, "
        f"{sum(len(s.steps) for s in shifts)} touchpoints, "
        f"{len({s.staff for s in shifts})} staff"
    )
    report_spatial_frame(shifts, res_stats)

    if args.cmd == "battery":
        run_battery(shifts, args.action, order=args.order)
    elif args.cmd == "ruleout":
        run_ruleout(shifts, args.action, use_bc=args.bc)
    else:
        run_sweep(shifts, args.action, use_bc=args.bc)


if __name__ == "__main__":
    main()
