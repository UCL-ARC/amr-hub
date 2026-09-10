"""
Build a synthetic DuckDB file matching the AMR-HUB schema.

Data.StaffLocationEvent + the Ref.* tables it joins against.
Usage: python make_synthetic_db.py --out synthetic_amr.duckdb.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta

import duckdb
import numpy as np

# staff, event_time, source_key, link_key, patient, interaction_type_key
EventRow = tuple[int, datetime, int, int | None, int | None, int]

# ====================================================================
# Reference Data: TODO Use real floor plan mapping.
# ====================================================================


# ---------------------------------------------------------------------
@dataclass
class ReferenceData:
    """Static schema/config data shared by shift emulation and DB writing."""

    visitable_rooms: list[str]
    department_rows: list[tuple]
    beds_by_room: dict[str, list[int]]
    door_rows: list[tuple]
    doors_by_room: dict[str, int]
    workstation_rows: list[tuple]
    mobile_workstation_key: int
    roster_rows: list[tuple]
    interaction_type_rows: list[tuple]
    flowsheet_itype_keys: list[int]
    staff_rows: list[tuple]
    staff_is_noisy: dict[int, bool]


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _build_reference_data(
    rng: np.random.Generator, n_staff: int, noisy_fraction: float
) -> ReferenceData:
    bays = ["Bay1", "Bay2", "Bay3"]
    beds_per_bay = 4
    triage_beds = 2

    department_rows = []  # (DepartmentKey, BedName, RoomName)
    dep_key = 1
    beds_by_room: dict[str, list[int]] = {}
    for bay in bays:
        beds_by_room[bay] = []
        for b in range(1, beds_per_bay + 1):
            department_rows.append((dep_key, f"{bay}-Bed{b}", bay))
            beds_by_room[bay].append(dep_key)
            dep_key += 1
    beds_by_room["Triage"] = []
    for b in range(1, triage_beds + 1):
        department_rows.append((dep_key, f"Triage-Bed{b}", "Triage"))
        beds_by_room["Triage"].append(dep_key)
        dep_key += 1

    visitable_rooms = [*bays, "Triage"]

    door_pairs = [
        ("Corridor", "Triage"),
        ("Corridor", "Bay1"),
        ("Corridor", "Bay2"),
        ("Corridor", "Bay3"),
        ("Corridor", "NurseStation"),
        ("Corridor", "BreakRoom"),
    ]
    door_rows = []  # (DoorKey, DoorName)
    doors_by_room: dict[str, int] = {}  # room : its Corridor door's DoorKey
    for i, (side_a, side_b) in enumerate(door_pairs, start=1):
        door_rows.append((i, f"{side_a} - {side_b}"))
        doors_by_room[side_b] = i

    # fixed workstations (resolve to a single room via place-workstations)
    # and one mobile "WOW" cart (resolves with low share, or stays unplaced).
    workstation_rows = [
        (1, "NurseStation WS1"),
        (2, "Bay2 WS1"),
        (3, "WOW Cart 1"),
    ]
    mobile_workstation_key = 3

    roster_rows = [(1, "Ward A Day"), (2, "Ward A Night")]

    interaction_type_rows = [
        (1, "Door Badge In", "Door Message"),
        (2, "Door Badge Out", "Door Message"),
        (3, "Workstation Login", "Workstation"),
        (4, "Vitals Entry", "Flowsheet"),
        (5, "Medication Administration", "Flowsheet"),
        (6, "Care Note", "Flowsheet"),
        (7, "Roster Start", "Roster"),
        (8, "Roster End", "Roster"),
    ]
    flowsheet_itype_keys = [4, 5, 6]

    role_choices = ["Nurse", "HCA", "Doctor"]
    role_weights = [0.6, 0.25, 0.15]
    staff_rows = []  # (MasterIndexId, Role)
    staff_is_noisy: dict[int, bool] = {}
    for staff_id in range(1, n_staff + 1):
        role = rng.choice(role_choices, p=role_weights)
        staff_rows.append((staff_id, role))
        staff_is_noisy[staff_id] = rng.random() < noisy_fraction

    return ReferenceData(
        visitable_rooms=visitable_rooms,
        department_rows=department_rows,
        beds_by_room=beds_by_room,
        door_rows=door_rows,
        doors_by_room=doors_by_room,
        workstation_rows=workstation_rows,
        mobile_workstation_key=mobile_workstation_key,
        roster_rows=roster_rows,
        interaction_type_rows=interaction_type_rows,
        flowsheet_itype_keys=flowsheet_itype_keys,
        staff_rows=staff_rows,
        staff_is_noisy=staff_is_noisy,
    )


# ---------------------------------------------------------------------

# ====================================================================

# ====================================================================
# Emulate Shifts
# ====================================================================


# ---------------------------------------------------------------------
def _emulate_shifts(  # noqa: PLR0915 sequential test-data gen, splitting
    # further would just scatter one linear narrative across more functions.
    rng: np.random.Generator,
    ref: ReferenceData,
    n_staff: int,
    n_days: int,
) -> list[EventRow]:
    # Naive by design: matches the naive `timestamp` DuckDB column type used
    # by both this generator and the real AMR-HUB schema.
    base_date = datetime(2024, 1, 1)  # noqa: DTZ001
    event_rows: list[EventRow] = []
    link_key_counter = [1]  # boxed so the nested functions below can mutate it

    # --------------------------------------------------------------------
    def door_event(t: datetime, staff: int, room: str, *, entering: bool) -> datetime:
        door_key = ref.doors_by_room[room]
        itype = 1 if entering else 2
        event_rows.append((staff, t, door_key, None, None, itype))
        return t + timedelta(seconds=int(rng.integers(10, 60)))

    # --------------------------------------------------------------------

    # --------------------------------------------------------------------
    def flowsheet_event(
        t: datetime, staff: int, room: str, patient_id: int
    ) -> datetime:
        bed_key = int(rng.choice(ref.beds_by_room[room]))
        itype = int(rng.choice(ref.flowsheet_itype_keys))
        event_rows.append((staff, t, bed_key, None, patient_id, itype))
        return t + timedelta(minutes=float(rng.uniform(1, 6)))

    # --------------------------------------------------------------------

    # --------------------------------------------------------------------
    def workstation_event(t: datetime, staff: int, workstation_key: int) -> datetime:
        event_rows.append((staff, t, workstation_key, None, None, 3))
        return t + timedelta(minutes=float(rng.uniform(1, 4)))

    # --------------------------------------------------------------------

    # --------------------------------------------------------------------
    def simulate_shift(staff: int, day: int, *, is_night: bool, noisy: bool) -> None:
        start_hour = 19 if is_night else 7
        t = base_date + timedelta(
            days=day, hours=start_hour, minutes=int(rng.integers(-15, 15))
        )
        shift_link_key = link_key_counter[0]
        link_key_counter[0] += 1
        roster_key = 2 if is_night else 1

        event_rows.append(
            (staff, t, roster_key, shift_link_key, None, 7)
        )  # Roster Start

        n_visits = int(rng.integers(8, 15))
        patient_of_bed: dict[int, int] = {}  # stable "patient in this bed today"

        for visit in range(n_visits):
            if noisy:
                room = str(rng.choice(ref.visitable_rooms))
                gap_before = timedelta(minutes=float(rng.uniform(5, 90)))
                gap_after = timedelta(minutes=float(rng.uniform(5, 90)))
                drop_return_leg = rng.random() < 0.35
            else:
                room = ref.visitable_rooms[visit % len(ref.visitable_rooms)]
                gap_before = timedelta(minutes=float(rng.uniform(0.5, 3)))
                gap_after = timedelta(minutes=float(rng.uniform(0.5, 3)))
                drop_return_leg = False

            t = t + gap_before
            t = door_event(t, staff, "NurseStation", entering=False)
            t = door_event(t, staff, room, entering=True)

            for bed_key_raw in rng.choice(
                ref.beds_by_room[room], size=int(rng.integers(1, 3)), replace=False
            ):
                bed_key = int(bed_key_raw)
                if bed_key not in patient_of_bed:
                    patient_of_bed[bed_key] = day * 1000 + bed_key
                t = flowsheet_event(t, staff, room, patient_of_bed[bed_key])

            # Fixed WS near its own room, or the mobile cart from wherever we are.
            roll = rng.random()
            if room == "Bay2" and roll < 0.5:
                t = workstation_event(t, staff, 2)
            elif roll < 0.15:
                t = workstation_event(t, staff, ref.mobile_workstation_key)

            if not drop_return_leg:
                t = door_event(t, staff, room, entering=False)
                t = door_event(t, staff, "NurseStation", entering=True)
            t = t + gap_after

            if roll < 0.1:
                t = workstation_event(t, staff, 1)  # NurseStation WS, on the way past

        if rng.random() < 0.05:  # drop roster end on a small fraction of shifts
            return
        event_rows.append((staff, t, roster_key, shift_link_key, None, 8))  # Roster End

    # --------------------------------------------------------------------

    for staff_id in range(1, n_staff + 1):
        noisy = ref.staff_is_noisy[staff_id]
        for day in range(n_days):
            if rng.random() < 0.15:  # a day off
                continue
            is_night = bool(rng.random() < 0.3)
            simulate_shift(staff_id, day, is_night=is_night, noisy=noisy)

    for _ in range(25):  # stray events outside any rostered shift
        staff_id = int(rng.integers(1, n_staff + 1))
        t = base_date + timedelta(
            days=int(rng.integers(0, n_days)), hours=int(rng.integers(2, 5))
        )
        room = str(rng.choice(ref.visitable_rooms))
        event_rows.append((staff_id, t, ref.doors_by_room[room], None, None, 1))

    event_rows.sort(key=lambda r: (r[0], r[1]))
    return event_rows


# ---------------------------------------------------------------------

# ====================================================================

# ====================================================================
# Write to DuckDB
# ====================================================================


# ---------------------------------------------------------------------
def _write_to_duckdb(
    out_path: str, ref: ReferenceData, event_rows: list[EventRow]
) -> None:
    conn = duckdb.connect(out_path)
    conn.execute("create schema if not exists Data")
    conn.execute("create schema if not exists Ref")

    conn.execute("""
        create or replace table Ref.InteractionType (
            InteractionTypeKey integer,
            InteractionType varchar,
            InteractionTypeClass varchar
        )
    """)
    conn.executemany(
        "insert into Ref.InteractionType values (?, ?, ?)", ref.interaction_type_rows
    )

    conn.execute(
        "create or replace table Ref.Staff (MasterIndexId integer, Role varchar)"
    )
    conn.executemany("insert into Ref.Staff values (?, ?)", ref.staff_rows)

    conn.execute("create or replace table Ref.Door (DoorKey integer, DoorName varchar)")
    conn.executemany("insert into Ref.Door values (?, ?)", ref.door_rows)

    conn.execute(
        "create or replace table Ref.Workstation "
        "(WorkstationKey integer, WorkstationName varchar)"
    )
    conn.executemany("insert into Ref.Workstation values (?, ?)", ref.workstation_rows)

    conn.execute(
        "create or replace table Ref.Roster (RosterKey integer, RosterName varchar)"
    )
    conn.executemany("insert into Ref.Roster values (?, ?)", ref.roster_rows)

    conn.execute("""
        create or replace table Ref.Department (
            DepartmentKey integer,
            BedName varchar,
            RoomName varchar
        )
    """)
    conn.executemany("insert into Ref.Department values (?, ?, ?)", ref.department_rows)

    conn.execute("""
        create or replace table Data.StaffLocationEvent (
            MasterIndexId integer,
            EventDateTime timestamp,
            SourceKey integer,
            LinkKey integer,
            PatientDurableKey integer,
            InteractionTypeKey integer
        )
    """)
    conn.executemany(
        "insert into Data.StaffLocationEvent values (?, ?, ?, ?, ?, ?)", event_rows
    )

    conn.close()


# ---------------------------------------------------------------------

# ====================================================================


# ====================================================================
# Generate
# ====================================================================
def generate(
    out_path: str,
    seed: int = 0,
    n_staff: int = 18,
    n_days: int = 14,
    noisy_fraction: float = 0.3,  # we use this to make "bad" data :-)
) -> None:
    """Build reference data, emulate shifts, and write a synthetic DuckDB file."""
    rng = np.random.default_rng(seed)
    ref = _build_reference_data(rng, n_staff, noisy_fraction)
    event_rows = _emulate_shifts(rng, ref, n_staff, n_days)
    _write_to_duckdb(out_path, ref, event_rows)

    n_noisy = sum(1 for v in ref.staff_is_noisy.values() if v)
    print(f"wrote {out_path}")  # noqa: T201
    print(  # noqa: T201
        f"  {len(event_rows)} events, {n_staff} staff, "
        f"{n_noisy} noisy / {n_staff - n_noisy} routine"
    )
    print(  # noqa: T201
        f"  {len(ref.department_rows)} beds across "
        f"{len(ref.visitable_rooms)} bay/triage rooms"
    )
    print(  # noqa: T201
        f"  {len(ref.door_rows)} doors, {len(ref.workstation_rows)} workstations "
        f"({ref.mobile_workstation_key} is the mobile WOW cart)"
    )


# ====================================================================


# ====================================================================
# main
# ====================================================================
def main() -> None:
    """CLI entry point: generate a synthetic AMR-HUB DuckDB file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", default="synthetic_amr.duckdb", help="output DuckDB path"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-staff", type=int, default=18)
    parser.add_argument("--n-days", type=int, default=14)
    parser.add_argument(
        "--noisy-fraction",
        type=float,
        default=0.3,
        help="fraction of staff whose room visits are random-order/ragged-timed "
        "instead of a fixed rotation (0.0 = fully routine, 1.0 = fully noisy)",
    )
    args = parser.parse_args()
    generate(
        out_path=args.out,
        seed=args.seed,
        n_staff=args.n_staff,
        n_days=args.n_days,
        noisy_fraction=args.noisy_fraction,
    )


# ====================================================================

# ---------------------------------------------------------------------
if __name__ == "__main__":
    main()
# ---------------------------------------------------------------------
