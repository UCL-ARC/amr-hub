"""
data_wrangler.py.

Phase 1: Extracts, cleans, and standardizes AMR-Hub hospital logs into
sequential trajectories.
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import csv
import pickle
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

import duckdb
import matplotlib as mpl

mpl.use("Agg")  # For the TRE
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

# ====================================================================
# 0] Config Vars
# ====================================================================
N_TIME_BUCKETS = 4
KEEP_UNROSTERED = False
MIN_SHIFT_EVENTS = 3
WORKSTATION_MAX_ANCHOR_GAP_MINUTES = 10
WORKSTATION_MIN_SUPPORT = 20
WORKSTATION_MIN_SHARE = 0.6
OCCUPANCY_WINDOW_MINUTES = 5
MAX_OCCUPANCY = 5
DOOR_MAIN_ENTRY_SHARE_THRESHOLD = 0.3

FALLBACK_PREFIX_BY_CLASS = {
    "Door Message": "door",
    "Workstation": "ws",
    "Flowsheet": "fs",
    "Roster": "roster",
}
FALLBACK_NAME_TABLES = {
    "Door Message": ("Ref.Door", "DoorKey", "DoorName"),
    "Workstation": ("Ref.Workstation", "WorkstationKey", "WorkstationName"),
    "Roster": ("Ref.Roster", "RosterKey", "RosterName"),
}
ROOM_JOIN_TABLES = {
    "Door Message": None,
    "Workstation": None,
    "Flowsheet": ("Ref.Department", "DepartmentKey", "RoomName"),
}

DOOR_NAME_SEPARATORS = r"\s+(?:-|–|—|<->|/|to)\s+"  # noqa: RUF001
# ====================================================================


# ====================================================================
# Data Structures used in the code
# ====================================================================


# ---------------------------------------------------------------------
@dataclass
class Step:
    """A single touchpoint event within a shift trajectory."""

    event_time: float
    location: str
    interaction_class: str
    interaction_type: str
    role: str
    patient: str | None
    time_bucket: int
    unit: str = "unknown"
    occupancy: int = 0
    minutes_into_shift: float = 0.0


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
@dataclass
class Shift:
    """A staff member's full sequence of touchpoints for one roster interval."""

    staff: str
    link_key: int
    unit: str = "unknown"
    steps: list[Step] = field(default_factory=list)


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
@dataclass
class DoorStats:
    """Per door badge counts and how often a door bounds a shift's door events."""

    badge_in: int = 0
    badge_out: int = 0
    staff: set[str] = field(default_factory=set)
    first_of_shift: int = 0
    last_of_shift: int = 0

    @property
    def total(self) -> int:
        """Total badge events (in + out) recorded for this door."""
        return self.badge_in + self.badge_out

    @property
    def boundary_share(self) -> float:
        """Fraction of this door's uses that were a shift's first or last door event."""
        if not self.total:
            return 0.0
        return (self.first_of_shift + self.last_of_shift) / self.total


# ---------------------------------------------------------------------

# ====================================================================

# ====================================================================
# Helper Functions and Mapping Logic
# ====================================================================


# ---------------------------------------------------------------------
def std_code(s: str) -> str:
    """Collapse whitespace and uppercase a name for stable dictkey matching."""
    return re.sub(r"\s+", " ", str(s).strip()).upper()


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _normalize_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _load_key_to_name_map(
    conn: duckdb.DuckDBPyConnection, table: str, key_col: str, name_col: str
) -> dict[int, str]:
    # table/col names come from the internal FALLBACK_NAME_TABLES config dict,
    rows = conn.execute(
        f"select {key_col}, {name_col} from {table}"  # noqa: S608
    ).fetchall()
    return {int(k): str(v) for k, v in rows if k is not None}


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _load_room_maps(
    conn: duckdb.DuckDBPyConnection, room_mapping_csv: str | None
) -> dict[str, dict[int, str]]:
    maps: dict[str, dict[int, str]] = {}

    spec = ROOM_JOIN_TABLES["Flowsheet"]
    if spec:
        try:
            # spec comes from the internal ROOM_JOIN_TABLES config dict, never
            # from user input.
            rows = conn.execute(
                f"select {spec[1]}, {spec[2]} from {spec[0]}"  # noqa: S608
            ).fetchall()
            maps["Flowsheet"] = {
                int(k): f"room:{std_code(r)}" for k, r in rows if k and r
            }
        except duckdb.Error as exc:
            # Optional enrichment: if the lookup query fails, continue with
            # other mapping sources and return partial maps.
            print(f"Skipping optional Flowsheet room-map lookup: {exc}", file=sys.stderr)

    try:
        door_names = _load_key_to_name_map(conn, *FALLBACK_NAME_TABLES["Door Message"])
        edges = {}
        for key, name in door_names.items():
            parts = [
                std_code(p) for p in re.split(DOOR_NAME_SEPARATORS, name) if p.strip()
            ]
            if len(parts) == 2:
                edges[key] = f"door:{'|'.join(sorted(parts))}"
        maps.setdefault("Door Message", {}).update(edges)
    except duckdb.Error:
        # Optional fallback mapping; ignore DB errors so wrangling can proceed
        # without door-edge normalization.
        pass

    if room_mapping_csv:
        with Path(room_mapping_csv).open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                room = (row.get("room") or "").strip()
                if room:
                    maps.setdefault(row["interaction_class"].strip(), {})[
                        int(row["source_key"])
                    ] = f"room:{std_code(room)}"
    return maps


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _resolve_location(
    cls: str, skey: int | None, room_maps: dict, fallback_maps: dict
) -> str:
    if skey is None:
        return f"{FALLBACK_PREFIX_BY_CLASS.get(cls, 'x')}:na"
    if symbol := room_maps.get(cls, {}).get(int(skey)):
        return symbol
    name = fallback_maps.get(cls, {}).get(int(skey), skey)
    return f"{FALLBACK_PREFIX_BY_CLASS.get(cls, 'x')}:{name}"


# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
_EVENTS_QUERY = """
select e.MasterIndexId, epoch(e.EventDateTime), e.SourceKey, e.LinkKey,
       e.PatientDurableKey, it.InteractionType, it.InteractionTypeClass,
       coalesce(s.Role, 'unknown')
from Data.StaffLocationEvent e
join Ref.InteractionType it on e.InteractionTypeKey = it.InteractionTypeKey
left join Ref.Staff s on s.MasterIndexId = e.MasterIndexId
order by e.MasterIndexId, e.EventDateTime
"""


def _load_events(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    return conn.execute(_EVENTS_QUERY).fetchall()


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _build_roster_intervals(
    rows: list[tuple], roster_names: dict[int, str]
) -> dict[str, list[tuple[float, float, int, str]]]:
    starts, ends = {}, {}
    for staff, t, skey, lkey, _pat, itype, icls, _role in rows:
        if icls == "Roster" and lkey is not None:
            if itype == "Roster Start":
                starts[(staff, int(lkey))] = (
                    float(t),
                    roster_names.get(int(skey) if skey else 0, "unknown"),
                )
            elif itype == "Roster End":
                ends[(staff, int(lkey))] = float(t)

    intervals = defaultdict(list)
    for key, (start_t, unit) in starts.items():
        if (end_t := ends.get(key)) and end_t > start_t:
            intervals[key[0]].append((start_t, end_t, key[1], unit))
    for staff in intervals:
        intervals[staff].sort()
    return intervals


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _annotate_occupancy_and_fatigue(shifts: list[Shift]) -> None:
    room_touchpoints = defaultdict(list)
    for shift in shifts:
        shift_start = shift.steps[0].event_time
        for step in shift.steps:
            step.minutes_into_shift = (step.event_time - shift_start) / 60.0
            if step.location.startswith("room:"):
                room_touchpoints[step.location].append((shift.staff, step))

    window_seconds = OCCUPANCY_WINDOW_MINUTES * 60.0
    for touchpoints in room_touchpoints.values():
        touchpoints.sort(key=lambda pair: pair[1].event_time)
        n = len(touchpoints)
        w_start, w_end = 0, 0
        for i in range(n):
            t = touchpoints[i][1].event_time
            while touchpoints[w_start][1].event_time < t - window_seconds:
                w_start += 1
            while w_end < n and touchpoints[w_end][1].event_time <= t + window_seconds:
                w_end += 1
            other_staff = {
                touchpoints[j][0]
                for j in range(w_start, w_end)
                if touchpoints[j][0] != touchpoints[i][0]
            }
            touchpoints[i][1].occupancy = min(len(other_staff), MAX_OCCUPANCY)


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _collect_door_stats(shifts: list[Shift]) -> dict[str, DoorStats]:
    # A door counted as a shift's first or last door class step disproportionately
    # behaves like a main entry/exit (staff arriving/leaving), versus a door
    # mostly seen mid shift, which behaves like an internal connector between rooms.
    # We can infer from location as per @ksuchak1990 for data quality it must be blind.
    stats: dict[str, DoorStats] = defaultdict(DoorStats)
    for shift in shifts:
        door_steps = [s for s in shift.steps if s.interaction_class == "Door Message"]
        for i, step in enumerate(door_steps):
            door = stats[step.location]
            if step.interaction_type == "Door Badge In":
                door.badge_in += 1
            elif step.interaction_type == "Door Badge Out":
                door.badge_out += 1
            door.staff.add(shift.staff)
            is_first, is_last = i == 0, i == len(door_steps) - 1
            if is_first and is_last:
                # A shift with only one door touchpoint has just one boundary
                # role, not two -- pick it from the recorded badge direction
                # so this single event isn't double-counted as both.
                if step.interaction_type == "Door Badge Out":
                    door.last_of_shift += 1
                else:
                    door.first_of_shift += 1
            elif is_first:
                door.first_of_shift += 1
            elif is_last:
                door.last_of_shift += 1
    return stats


# ---------------------------------------------------------------------

# ====================================================================


# ====================================================================
# Core Extraction
# ====================================================================


# ---------------------------------------------------------------------
def load_shifts(
    conn: duckdb.DuckDBPyConnection, room_mapping_csv: str | None = None
) -> list[Shift]:
    """Extract per shift touchpoint sequences from the raw event log."""
    room_maps = _load_room_maps(conn, room_mapping_csv)
    fallback_maps = {
        c: _load_key_to_name_map(conn, t, k, n)
        for c, (t, k, n) in FALLBACK_NAME_TABLES.items()
    }
    roster_names = fallback_maps.get("Roster", {})

    rows = _load_events(conn)
    intervals = _build_roster_intervals(rows, roster_names)

    shifts = {}
    for staff, t_raw, skey, _lkey, pat, itype, icls, role in rows:
        if icls == "Roster":
            continue
        t = float(t_raw)
        hit = next(
            ((lk, u) for st, et, lk, u in intervals.get(staff, []) if st <= t <= et),
            None,
        )
        if not hit and not KEEP_UNROSTERED:
            continue
        shift_key = (staff, hit[0] if hit else -1)

        if shift_key not in shifts:
            shifts[shift_key] = Shift(
                staff=staff, link_key=shift_key[1], unit=hit[1] if hit else "unknown"
            )

        shifts[shift_key].steps.append(
            Step(
                event_time=t,
                location=_resolve_location(icls, skey, room_maps, fallback_maps),
                interaction_class=icls,
                interaction_type=itype,
                role=str(role),
                patient=str(pat) if pat else None,
                time_bucket=min(
                    N_TIME_BUCKETS - 1, int(((t % 86400) / 86400) * N_TIME_BUCKETS)
                ),
                unit=shifts[shift_key].unit,
            )
        )

    kept = [s for s in shifts.values() if len(s.steps) >= MIN_SHIFT_EVENTS]
    for s in kept:
        s.steps.sort(key=lambda x: x.event_time)
    _annotate_occupancy_and_fatigue(kept)
    return kept


# ---------------------------------------------------------------------

# ====================================================================


# ====================================================================
# Workstation Placement: TODO: Check if this missing data cant be inferred.
# ====================================================================


# ---------------------------------------------------------------------
def _write_workstation_placements(
    out_path: str,
    workstation_names: dict[int, str],
    votes: dict[int, Counter],
    gap_totals: dict[int, dict[str, float]],
    confidence_thresholds: tuple[int, float],
) -> int:
    min_support, min_share = confidence_thresholds
    n_confident = 0
    with Path(out_path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "interaction_class",
                "source_key",
                "name_hint",
                "room",
                "support",
                "share",
                "runner_up",
                "avg_gap_min",
            ]
        )
        for sk in sorted(workstation_names):
            counts = votes.get(sk, Counter())
            support = sum(counts.values())
            if support == 0:
                writer.writerow(
                    ["Workstation", sk, workstation_names[sk], "", 0, "", "", ""]
                )
                continue
            ranked = counts.most_common(2)
            best_room, best_n = ranked[0]
            runner_up = ranked[1][0].removeprefix("room:") if len(ranked) > 1 else ""
            share = best_n / support
            confident = support >= min_support and share >= min_share
            room = best_room.removeprefix("room:") if confident else ""
            avg_gap_min = (gap_totals[sk][best_room] / best_n) / 60.0
            if confident:
                n_confident += 1
            writer.writerow(
                [
                    "Workstation",
                    sk,
                    workstation_names[sk],
                    room,
                    support,
                    f"{share:.2f}",
                    runner_up,
                    f"{avg_gap_min:.1f}",
                ]
            )
    return n_confident


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def run_place_workstations(
    conn: duckdb.DuckDBPyConnection,
    out_path: str,
    max_gap_minutes: int = WORKSTATION_MAX_ANCHOR_GAP_MINUTES,
    min_support: int = WORKSTATION_MIN_SUPPORT,
    min_share: float = WORKSTATION_MIN_SHARE,
) -> None:
    """Vote each Workstation login to the room of its nearest flowsheet anchor."""
    # Nearest anchor position interpolation: each Workstation login votes for
    # its closest intime Flowsheet room by the same staff member. A login
    # whose nearest anchor is more than max_gap_minutes away casts no vote
    # a stale anchor is worse than no anchor :-).
    room_maps = _load_room_maps(conn, None)
    flowsheet_rooms = room_maps.get("Flowsheet", {})
    if not flowsheet_rooms:
        msg = "[place-workstations] no flowsheet room mapping available."
        raise SystemExit(msg)
    workstation_names = _load_key_to_name_map(
        conn, *FALLBACK_NAME_TABLES["Workstation"]
    )

    rows = conn.execute("""
        select e.MasterIndexId, epoch(e.EventDateTime), e.SourceKey,
               it.InteractionTypeClass
        from Data.StaffLocationEvent e
        join Ref.InteractionType it on e.InteractionTypeKey = it.InteractionTypeKey
        where it.InteractionTypeClass in ('Workstation', 'Flowsheet')
          and e.SourceKey is not null
        order by e.MasterIndexId, e.EventDateTime
        """).fetchall()

    max_gap_seconds = max_gap_minutes * 60.0
    votes: dict[int, Counter] = defaultdict(Counter)
    gap_totals: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    n_skipped = 0

    for _staff, group in groupby(rows, key=lambda r: r[0]):
        events = [(float(t), int(sk), cls) for _s, t, sk, cls in group]
        anchors = [
            (t, flowsheet_rooms[sk])
            for t, sk, cls in events
            if cls == "Flowsheet" and sk in flowsheet_rooms
        ]
        if not anchors:
            continue
        anchor_times = [t for t, _ in anchors]
        anchor_rooms = [r for _, r in anchors]
        for t, sk, cls in events:
            if cls != "Workstation":
                continue
            idx = bisect.bisect_left(anchor_times, t)
            candidates = [i for i in (idx - 1, idx) if 0 <= i < len(anchor_times)]
            nearest = min(candidates, key=lambda i: abs(anchor_times[i] - t))
            gap = abs(anchor_times[nearest] - t)
            if gap > max_gap_seconds:
                n_skipped += 1
                continue
            room = anchor_rooms[nearest]
            votes[sk][room] += 1
            gap_totals[sk][room] += gap

    n_confident = _write_workstation_placements(
        out_path, workstation_names, votes, gap_totals, (min_support, min_share)
    )
    print(  # noqa: T201 CLI progress output, this module's actual interface
        f"[place-workstations] {n_confident}/{len(workstation_names)} placed "
        f"(nearest anchor <= {max_gap_minutes}min, support>={min_support}, "
        f"share>={min_share}; {n_skipped} logins skipped)."
    )
    print(  # noqa: T201
        f"[place-workstations] wrote {out_path}. Blank rooms are unresolved "
        "review and pass back via room-mapping."
    )


# ---------------------------------------------------------------------

# ====================================================================


# ====================================================================
# Logging
# ====================================================================


# ---------------------------------------------------------------------
class _Tee:
    """Write to multiple text streams at once (stdout + a log file)."""

    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        """Write `data` to every wrapped stream, returning its length."""
        for stream in self._streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        """Flush every wrapped stream."""
        for stream in self._streams:
            stream.flush()


# ---------------------------------------------------------------------

# ====================================================================


# ====================================================================
# Plotting
# ====================================================================
_PLOT_SURFACE = "#fcfcfb"
_PLOT_INK_PRIMARY = "#0b0b0b"
_PLOT_INK_SECONDARY = "#52514e"
_PLOT_INK_MUTED = "#898781"
_PLOT_GRIDLINE = "#e1e0d9"
_PLOT_AXIS = "#c3c2b7"
_PLOT_COLOR_RESOLVED = "#0ca30c"
_PLOT_COLOR_UNRESOLVED = "#d03b3b"
_PLOT_COLOR_BADGE_IN = "#2a78d6"
_PLOT_COLOR_BADGE_OUT = "#eb6834"
_PLOT_COLOR_HIST = "#2a78d6"


# ---------------------------------------------------------------------
def _new_figure(title: str, xlabel: str, ylabel: str) -> tuple[Figure, Axes]:
    fig, ax = plt.subplots(figsize=(9, 5), facecolor=_PLOT_SURFACE)
    ax.set_facecolor(_PLOT_SURFACE)
    ax.set_title(title, color=_PLOT_INK_PRIMARY, fontsize=12, pad=12)
    ax.set_xlabel(xlabel, color=_PLOT_INK_SECONDARY)
    ax.set_ylabel(ylabel, color=_PLOT_INK_SECONDARY)
    ax.tick_params(colors=_PLOT_INK_MUTED)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(_PLOT_AXIS)
    ax.grid(axis="both", color=_PLOT_GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    return fig, ax


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _plot_mapping_coverage(
    class_coverage: list[tuple[str, int, int]], out_dir: Path
) -> None:
    """Save a stacked resolved/unresolved bar chart per interaction class."""
    labels = [*(icls for icls, _, _ in class_coverage), "TOTAL"]
    n_keys = [n for _, n, _ in class_coverage]
    resolved = [r for _, _, r in class_coverage]
    n_keys.append(sum(n_keys))
    resolved.append(sum(resolved))
    unresolved = [n - r for n, r in zip(n_keys, resolved, strict=True)]

    fig, ax = _new_figure("Mapping Coverage by Interaction Class", "", "source keys")
    x = range(len(labels))
    ax.bar(x, resolved, color=_PLOT_COLOR_RESOLVED, label="resolved", zorder=2)
    ax.bar(
        x,
        unresolved,
        bottom=resolved,
        color=_PLOT_COLOR_UNRESOLVED,
        label="unresolved",
        zorder=2,
    )
    headroom = max(n_keys) * 0.02 if n_keys else 0
    for i, (n, r) in enumerate(zip(n_keys, resolved, strict=True)):
        if n:
            ax.text(
                i,
                n + headroom,
                f"{r}/{n}",
                ha="center",
                va="bottom",
                color=_PLOT_INK_SECONDARY,
                fontsize=8,
            )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, color=_PLOT_INK_PRIMARY, rotation=20, ha="right")
    ax.legend(frameon=False, labelcolor=_PLOT_INK_SECONDARY)
    fig.tight_layout()
    fig.savefig(str(out_dir / "mapping_coverage.png"), dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _plot_door_usage(door_stats: dict[str, DoorStats], out_dir: Path) -> None:
    """Save a horizontal badge in/out bar chart, direct-labelled MAIN/internal."""
    ranked = sorted(door_stats.items(), key=lambda kv: -kv[1].total)
    if not ranked:
        return
    doors = [door for door, _ in ranked]
    stats = [stat for _, stat in ranked]

    fig, ax = _new_figure("Door Usage: Badge In/Out", "badge events", "")
    y = list(range(len(doors)))
    bar_height = 0.35
    ax.barh(
        [i + bar_height / 2 for i in y],
        [s.badge_in for s in stats],
        height=bar_height,
        color=_PLOT_COLOR_BADGE_IN,
        label="in",
        zorder=2,
    )
    ax.barh(
        [i - bar_height / 2 for i in y],
        [s.badge_out for s in stats],
        height=bar_height,
        color=_PLOT_COLOR_BADGE_OUT,
        label="out",
        zorder=2,
    )
    max_total = max(s.total for s in stats)
    for i, stat in enumerate(stats):
        classification = (
            "MAIN"
            if stat.boundary_share >= DOOR_MAIN_ENTRY_SHARE_THRESHOLD
            else "internal"
        )
        ax.text(
            max(stat.badge_in, stat.badge_out) + max_total * 0.02,
            i,
            classification,
            va="center",
            color=_PLOT_INK_SECONDARY,
            fontsize=8,
        )
    ax.set_yticks(y)
    ax.set_yticklabels(doors, color=_PLOT_INK_PRIMARY, fontsize=8)
    ax.invert_yaxis()
    ax.legend(frameon=False, labelcolor=_PLOT_INK_SECONDARY)
    fig.tight_layout()
    fig.savefig(str(out_dir / "door_usage.png"), dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _plot_shift_length_histogram(shifts: list[Shift], out_dir: Path) -> None:
    """Save a histogram of the number of steps per shift."""
    lengths = [len(s.steps) for s in shifts]
    if not lengths:
        return
    fig, ax = _new_figure("Shift Length Distribution", "steps per shift", "shifts")
    n_bins = min(30, max(1, len(set(lengths))))
    ax.hist(lengths, bins=n_bins, color=_PLOT_COLOR_HIST, zorder=2)
    fig.tight_layout()
    fig.savefig(str(out_dir / "shift_length_histogram.png"), dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------

# ====================================================================


# ====================================================================
# Diagnostic Report: Basic stats
# ====================================================================


# ---------------------------------------------------------------------
def _print_diagnostics(
    conn: duckdb.DuckDBPyConnection, seed: int
) -> tuple[list[Shift], list[tuple[str, int, int]], dict[str, DoorStats]]:
    events = _load_events(conn)
    roster_names = _load_key_to_name_map(conn, *FALLBACK_NAME_TABLES["Roster"])
    intervals = _build_roster_intervals(events, roster_names)
    shifts = load_shifts(conn)

    n_staff = len({staff for staff, *_ in events})
    n_intervals = sum(len(v) for v in intervals.values())
    n_units = len({u for ivs in intervals.values() for _, _, _, u in ivs})
    print(  # noqa: T201
        f"[summary] events={len(events)} staff={n_staff} "
        f"valid_roster_intervals={n_intervals} roster_units={n_units} "
        f"shifts_kept(>={MIN_SHIFT_EVENTS}events)={len(shifts)}"
    )

    room_maps = _load_room_maps(conn, None)
    fallback_maps = {
        c: _load_key_to_name_map(conn, t, k, n)
        for c, (t, k, n) in FALLBACK_NAME_TABLES.items()
    }
    keys_by_class = defaultdict(set)
    for _staff, _t, skey, _lkey, _pat, _itype, icls, _role in events:
        if icls != "Roster" and skey is not None:
            keys_by_class[icls].add(int(skey))

    print(  # noqa: T201
        f"[mapping-coverage] {'class':20s} {'n_keys':>7s} "
        f"{'resolved':>9s} {'coverage':>9s}"
    )
    class_coverage: list[tuple[str, int, int]] = []
    total_keys = total_resolved = 0
    for icls, keys in sorted(keys_by_class.items()):
        resolved = sum(
            1
            for sk in keys
            if _resolve_location(icls, sk, room_maps, fallback_maps).startswith(
                ("room:", "door:")
            )
        )
        class_coverage.append((icls, len(keys), resolved))
        total_keys += len(keys)
        total_resolved += resolved
        print(  # noqa: T201
            f"[mapping-coverage] {icls:20s} {len(keys):7d} {resolved:9d} "
            f"{resolved / len(keys):9.1%}"
        )
    print(  # noqa: T201
        f"[mapping-coverage] {'TOTAL':20s} {total_keys:7d} {total_resolved:9d} "
        f"{total_resolved / max(1, total_keys):9.1%}"
    )

    door_stats = _collect_door_stats(shifts)
    print(  # noqa: T201
        f"\n[door-usage] {'door':32s} {'in':>5s} {'out':>5s} {'staff':>5s} "
        f"{'boundary%':>9s} {'class':>8s}"
    )
    for door, stat in sorted(door_stats.items(), key=lambda kv: -kv[1].total):
        classification = (
            "MAIN"
            if stat.boundary_share >= DOOR_MAIN_ENTRY_SHARE_THRESHOLD
            else "internal"
        )
        print(  # noqa: T201
            f"[door-usage] {door:32s} {stat.badge_in:5d} {stat.badge_out:5d} "
            f"{len(stat.staff):5d} {stat.boundary_share:9.1%} {classification:>8s}"
        )

    # deterministic sampling for a diagnostic report
    shift = random.Random(seed).choice(shifts)  # noqa: S311
    print(  # noqa: T201
        f"\n[example-sequence] staff={shift.staff} unit={shift.unit} "
        f"link_key={shift.link_key} n_steps={len(shift.steps)}"
    )
    for step in shift.steps:
        print(  # noqa: T201
            f"  t={step.minutes_into_shift:7.1f}min  {step.location:22s} "
            f"{step.interaction_class:14s} {step.interaction_type:20s} "
            f"occ={step.occupancy}"
        )

    return shifts, class_coverage, door_stats


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def run_report(
    conn: duckdb.DuckDBPyConnection,
    seed: int = 0,
    out_dir: str = "./simulation_outputs",
) -> None:
    """
    Print diagnostics to stdout and out_dir/duckdb_analysis.log, plus plots.

    Writes mapping_coverage.png, door_usage.png, and
    shift_length_histogram.png alongside the log.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    log_path = out_path / "duckdb_analysis.log"

    with (
        log_path.open("w", encoding="utf-8") as log_file,
        # _Tee only duck-types write()/flush(), not the full TextIO interface
        # redirect_stdout's TypeVar is bound to.
        contextlib.redirect_stdout(_Tee(sys.stdout, log_file)),  # type: ignore[type-var]
    ):
        shifts, class_coverage, door_stats = _print_diagnostics(conn, seed)

        _plot_mapping_coverage(class_coverage, out_path)
        _plot_door_usage(door_stats, out_path)
        _plot_shift_length_histogram(shifts, out_path)

        print(f"\n[report] wrote {log_path} and 3 plot(s) to {out_path}/")  # noqa: T201


# ---------------------------------------------------------------------


# ====================================================================
# main
# ====================================================================
def main() -> None:
    """Entry point: extract / place workstations / report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("cmd", choices=["extract", "place-workstations", "report"])
    parser.add_argument("--room-mapping", default=None)
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "trajectories.pkl for extract, "
            "workstation_room_mapping.csv for place-workstations"
        ),
    )
    parser.add_argument(
        "--seed", type=int, default=0, help="report: which shift example sequence picks"
    )
    parser.add_argument(
        "--out-dir",
        default="./simulation_outputs",
        help="report: directory for duckdb_analysis.log and plots",
    )
    args = parser.parse_args()

    conn = duckdb.connect(args.db, read_only=True)

    if args.cmd == "extract":
        out_path = args.out or "trajectories.pkl"
        print(" !Extracting Trajectories! ")  # noqa: T201
        shifts = load_shifts(conn, args.room_mapping)
        print(f"Loaded {len(shifts)} valid shifts. Saving to {out_path}")  # noqa: T201
        with Path(out_path).open("wb") as f:
            pickle.dump(shifts, f)
        print("Done")  # noqa: T201
    elif args.cmd == "place-workstations":
        run_place_workstations(
            conn, out_path=args.out or "workstation_room_mapping.csv"
        )
    elif args.cmd == "report":
        run_report(conn, seed=args.seed, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
# ====================================================================
