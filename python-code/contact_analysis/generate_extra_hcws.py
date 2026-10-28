"""
Generate additional healthcare-worker (HCW) location events.

Reads an existing location-event table, then adds ``--n-extra-hcws`` synthetic
HCWs active over the same time window. Each extra HCW alternates workstation
work with patient rounds and occasional WC and restaurant visits. The result is
written as a CSV and a schema-v1 DuckDB file; the input is left untouched.

The route table below is specific to the ``tests/inputs/buildings.yml`` layout
(Staff Room, Ward, Corridor, WC, Restaurant on one floor). Run from
``python-code/``::

    uv run python contact_analysis/generate_extra_hcws.py --n-extra-hcws 4
"""

import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from amr_hub_abm.config import (
    LocationTimeseriesDataConfig,
    LocationTimeseriesDataFormat,
)
from amr_hub_abm.location_data import (
    BASE_COLUMNS,
    CANONICAL_COLUMNS,
    DUCKDB_COLUMN_TYPES,
    DUCKDB_METADATA_TABLE,
    LOCATION_SCHEMA_COMPONENT,
    LOCATION_SCHEMA_VERSION,
    read_location_timeseries,
)
from amr_hub_abm.spatial.furniture import ContentType

BUILDING = "Sample Hospital:0"
STAFF_ROOM = f"{BUILDING}:Staff Room"
CORRIDOR = f"{BUILDING}:Corridor"
WARD = f"{BUILDING}:Ward"
WC = f"{BUILDING}:WC"
RESTAURANT = f"{BUILDING}:Restaurant"

# Global door ids: each room's own door and the matching corridor-side door.
DOOR_STAFF = 1
DOOR_WARD = 0
DOOR_WC = 2
DOOR_RESTAURANT = 3

Event = tuple[pd.Timestamp, str, str, int | None, int | None, int | None]


def _ts(start: pd.Timestamp, minutes: int) -> pd.Timestamp:
    """Return ``start`` shifted by whole minutes."""
    return start + pd.Timedelta(minutes=minutes)


def _leave_staff_room(start: pd.Timestamp, minute: int) -> list[Event]:
    """Leave the Staff Room and arrive in the Corridor one minute later."""
    return [(_ts(start, minute), STAFF_ROOM, "door_access", None, DOOR_STAFF, None)]


def _return_to_staff_room(start: pd.Timestamp, minute: int) -> list[Event]:
    """Re-enter the Staff Room from the Corridor and resume workstation work."""
    return [
        (_ts(start, minute), CORRIDOR, "door_access", None, DOOR_STAFF, None),
        (_ts(start, minute + 1), STAFF_ROOM, "workstation", None, None, None),
    ]


def patient_round(
    start: pd.Timestamp, patients: list[int], rng: np.random.Generator
) -> tuple[list[Event], int]:
    """Build a round of all patients; return events and duration in minutes."""
    events = _leave_staff_room(start, 0)
    events.append((_ts(start, 1), CORRIDOR, "door_access", None, DOOR_WARD, None))
    minute = 4
    for patient in rng.permutation(patients):
        events.append(
            (_ts(start, minute), WARD, "attend_patient", int(patient), None, None)
        )
        minute += 2
    minute += 6
    events.append((_ts(start, minute), WARD, "door_access", None, DOOR_WARD, None))
    events.extend(_return_to_staff_room(start, minute + 1))
    return events, minute + 2


def amenity_visit(
    start: pd.Timestamp, room: str, door: int, content: ContentType, dwell: int
) -> tuple[list[Event], int]:
    """Build a WC or restaurant visit; return events and duration in minutes."""
    events = _leave_staff_room(start, 0)
    events.append((_ts(start, 1), CORRIDOR, "door_access", None, door, None))
    events.append((_ts(start, 3), room, "occupy_content", None, None, int(content)))
    leave = 3 + dwell
    events.append((_ts(start, leave), room, "door_access", None, door, None))
    events.extend(_return_to_staff_room(start, leave + 1))
    return events, leave + 3


def hcw_schedule(
    window: tuple[pd.Timestamp, pd.Timestamp],
    patients: list[int],
    probabilities: tuple[float, float],
    max_start_offset: int,
    rng: np.random.Generator,
) -> list[Event]:
    """Generate one HCW's events, ending no later than the window end."""
    start, end = window
    wc_prob, restaurant_prob = probabilities
    minute = int(rng.integers(0, max_start_offset + 1))
    events: list[Event] = [
        (_ts(start, minute), STAFF_ROOM, "workstation", *(None,) * 3)
    ]
    last_minute = int((end - start).total_seconds() // 60)

    while True:
        minute += int(rng.integers(10, 31))
        draw = rng.random()
        if draw < wc_prob:
            block, length = amenity_visit(
                _ts(start, minute),
                WC,
                DOOR_WC,
                ContentType.TOILET,
                int(rng.integers(5, 13)),
            )
        elif draw < wc_prob + restaurant_prob:
            block, length = amenity_visit(
                _ts(start, minute),
                RESTAURANT,
                DOOR_RESTAURANT,
                ContentType.CHAIR,
                int(rng.integers(10, 26)),
            )
        else:
            block, length = patient_round(_ts(start, minute), patients, rng)
        if minute + length > last_minute:
            return events
        events.extend(block)
        minute += length


def to_frame(events: list[tuple[int, Event]]) -> pd.DataFrame:
    """Convert ``(hcw_id, event)`` pairs to base-column rows."""
    rows = [
        (
            hcw_id,
            timestamp,
            location,
            event_type,
            patient_id,
            door_id,
            content_type,
        )
        for hcw_id, (
            timestamp,
            location,
            event_type,
            patient_id,
            door_id,
            content_type,
        ) in events
    ]
    return pd.DataFrame(rows, columns=list(BASE_COLUMNS))


def combine(base: pd.DataFrame, extra: pd.DataFrame) -> pd.DataFrame:
    """Merge events, sort by time, and assign positive ``event_sequence`` ids."""
    combined = pd.concat(
        [base.loc[:, list(BASE_COLUMNS)].astype(object), extra.astype(object)],
        ignore_index=True,
    )
    combined["timestamp"] = pd.to_datetime(combined["timestamp"])
    combined = combined.sort_values(["timestamp", "hcw_id"], kind="stable")
    combined.insert(0, "event_sequence", range(1, len(combined) + 1))
    return combined.reset_index(drop=True)


def write_csv(data: pd.DataFrame, path: Path) -> None:
    """Write the legacy CSV layout with ``-`` for missing values."""
    out = data.loc[:, list(BASE_COLUMNS)].astype(object).where(data.notna(), "-")
    out.to_csv(path, index=False)


def write_duckdb(data: pd.DataFrame, path: Path, table: str) -> None:
    """Write a schema-v1 DuckDB file with typed columns and metadata."""
    path.unlink(missing_ok=True)
    columns = ", ".join(
        f"{name} {DUCKDB_COLUMN_TYPES[name]}" for name in CANONICAL_COLUMNS
    )
    typed = data.loc[:, list(CANONICAL_COLUMNS)].copy()
    for column in ("patient_id", "door_id", "content_type", "hcw_id"):
        typed[column] = typed[column].astype("Int64")
    with duckdb.connect(str(path)) as connection:
        connection.execute(f'CREATE TABLE "{table}" ({columns})')
        connection.register("events", typed)
        connection.execute(f'INSERT INTO "{table}" SELECT * FROM events')  # noqa: S608
        connection.execute(
            f"CREATE TABLE {DUCKDB_METADATA_TABLE} "
            "(component VARCHAR, schema_version INTEGER)"
        )
        connection.execute(
            f"INSERT INTO {DUCKDB_METADATA_TABLE} VALUES (?, ?)",  # noqa: S608
            [LOCATION_SCHEMA_COMPONENT, LOCATION_SCHEMA_VERSION],
        )


def main() -> None:
    """Generate extra HCW events and write the CSV and DuckDB outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        type=Path,
        default=Path("tests/inputs/location_timeseries.duckdb"),
    )
    parser.add_argument("--table", default="location_timeseries")
    parser.add_argument(
        "--output-stem",
        type=Path,
        default=Path("tests/inputs/location_timeseries_extra"),
        help="Writes <stem>.csv and <stem>.duckdb.",
    )
    parser.add_argument("--n-extra-hcws", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--wc-prob", type=float, default=0.15)
    parser.add_argument("--restaurant-prob", type=float, default=0.1)
    parser.add_argument("--max-start-offset-minutes", type=int, default=20)
    args = parser.parse_args()

    source = LocationTimeseriesDataConfig(
        format=LocationTimeseriesDataFormat.DUCKDB, path=args.base, table=args.table
    )
    base = read_location_timeseries(source)
    window = (
        pd.Timestamp(base["timestamp"].min()),
        pd.Timestamp(base["timestamp"].max()),
    )
    patients = sorted(int(p) for p in base["patient_id"].dropna().unique())
    first_id = int(base["hcw_id"].max()) + 1

    rng = np.random.default_rng(args.seed)
    events: list[tuple[int, Event]] = []
    for hcw_id in range(first_id, first_id + args.n_extra_hcws):
        schedule = hcw_schedule(
            window,
            patients,
            (args.wc_prob, args.restaurant_prob),
            args.max_start_offset_minutes,
            rng,
        )
        events.extend((hcw_id, event) for event in schedule)

    combined = combine(base, to_frame(events))
    csv_path = args.output_stem.with_suffix(".csv")
    duckdb_path = args.output_stem.with_suffix(".duckdb")
    write_csv(combined, csv_path)
    write_duckdb(combined, duckdb_path, args.table)
    print(  # noqa: T201
        f"Added {args.n_extra_hcws} HCWs ({len(events)} events); "
        f"wrote {csv_path} and {duckdb_path}"
    )


if __name__ == "__main__":
    main()
