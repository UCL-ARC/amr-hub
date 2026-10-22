#!/usr/bin/env python3
"""AMR-HUB progress report: roster, door, workstation and mapping-coverage summaries.

The database is attached read-only as catalog ``output``. Writes CSVs and PNGs to
/outputs/progress_report. Staff and patient IDs are not written; the example sequence
and door/workstation tables contain timestamps and reference names.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DEFAULT_DATA_DIR = Path("/data")
DEFAULT_OUTPUT_DIR = Path("/outputs/progress_report")
DEFAULT_CROSSWALK = Path("/outputs/ws_crosswalk.csv")

WS_WINDOW_MIN = 10
WS_MIN_SUPPORT = 20
WS_MIN_SHARE = 0.60

CLASS_PREFIX = {
    "Door Message": "door",
    "Workstation": "ws",
    "Flowsheet": "fs",
    "Roster": "roster",
}

SOURCE_REF = {
    "Door Message": ("Ref.Door", "DoorKey", "DoorName"),
    "Workstation": ("Ref.Workstation", "WorkstationKey", "WorkstationName"),
    "Roster": ("Ref.Roster", "RosterKey", "RosterName"),
}

ROOM_RESOLUTION = {
    "Flowsheet": ("Ref.Department", "DepartmentKey", "RoomName"),
}

# Door code, optionally prefixed by building/floor (e.g. E01XX000).
DOOR_CODE_RE = re.compile(
    r"\b(?:E\d{2})?[A-Z]{2}\d{2,3}[A-Z]?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidShift:
    staff: str
    link_key: int
    shift_start: Any
    shift_end: Any
    roster_key: int | None
    roster_unit: str
    activity_events: int


def quote_ident(name: str) -> str:
    """Quote a DuckDB identifier safely."""
    return '"' + name.replace('"', '""') + '"'


def sql_string(value: str | Path) -> str:
    """Quote a string for use as a DuckDB SQL literal."""
    return "'" + str(value).replace("'", "''") + "'"


def find_database(db_arg: str | None, data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    """Resolve an explicit DB path, a filename under /data, or the sole DB file."""
    if db_arg:
        candidate = Path(db_arg)
        if candidate.is_file():
            return candidate.resolve()
        under_data = data_dir / db_arg
        if under_data.is_file():
            return under_data.resolve()
        raise FileNotFoundError(
            f"Database not found: {db_arg!r}. Checked that path and {under_data}."
        )

    matches = sorted(
        {
            *data_dir.glob("*.db"),
            *data_dir.glob("*.duckdb"),
        }
    )
    if not matches:
        raise FileNotFoundError(
            f"No .db or .duckdb file found in {data_dir}. Pass --db explicitly."
        )
    if len(matches) > 1:
        listing = "\n".join(f"  - {p.name}" for p in matches)
        raise RuntimeError(
            "Multiple database files found. Pass --db with the filename:\n" + listing
        )
    return matches[0].resolve()


def connect_database(
    db_path: Path, catalog_alias: str = "output"
) -> duckdb.DuckDBPyConnection:
    """Attach the real DB under the catalog name expected by stored views."""
    con = duckdb.connect(":memory:")
    alias = quote_ident(catalog_alias)
    con.execute(f"ATTACH {sql_string(db_path)} AS {alias} (READ_ONLY)")
    con.execute(f"USE {alias}")
    return con


def table_columns(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> set[str]:
    rows = con.execute(
        """
        select column_name
        from information_schema.columns
        where lower(table_schema) = lower(?)
          and lower(table_name) = lower(?)
        """,
        [schema, table],
    ).fetchall()
    return {str(row[0]) for row in rows}


def require_tables(con: duckdb.DuckDBPyConnection) -> None:
    required = [
        ("Data", "StaffLocationEvent"),
        ("Ref", "InteractionType"),
        ("Ref", "Staff"),
        ("Ref", "Roster"),
        ("Ref", "Door"),
        ("Ref", "Workstation"),
        ("Ref", "Department"),
    ]
    missing: list[str] = []
    for schema, table in required:
        exists = con.execute(
            """
            select count(*)
            from information_schema.tables
            where lower(table_schema) = lower(?)
              and lower(table_name) = lower(?)
            """,
            [schema, table],
        ).fetchone()[0]
        if not exists:
            missing.append(f"{schema}.{table}")
    if missing:
        raise RuntimeError("Missing required database objects: " + ", ".join(missing))


def std_code(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def load_ref_map(
    con: duckdb.DuckDBPyConnection,
    table: str,
    key_col: str,
    name_col: str,
) -> dict[int, str]:
    rows = con.execute(f"select {key_col}, {name_col} from {table}").fetchall()
    return {
        int(key): str(name)
        for key, name in rows
        if key is not None and name is not None
    }


def parse_door_points(door_names: dict[int, str]) -> dict[int, str]:
    """Extract a one-point door code while keeping DoorKey uniqueness."""
    out: dict[int, str] = {}
    for door_key, name in door_names.items():
        match = DOOR_CODE_RE.search(std_code(name))
        if match is None:
            continue
        code = match.group(0).upper()
        out[door_key] = f"doorpoint:{code}#DOORKEY:{door_key}"
    return out


def load_flowsheet_rooms(con: duckdb.DuckDBPyConnection) -> dict[int, str]:
    table, key_col, room_col = ROOM_RESOLUTION["Flowsheet"]
    rows = con.execute(f"select {key_col}, {room_col} from {table}").fetchall()
    return {
        int(key): f"room:{std_code(room)}"
        for key, room in rows
        if key is not None and room is not None and str(room).strip()
    }


def infer_workstation_crosswalk(
    con: duckdb.DuckDBPyConnection,
    out_path: Path,
    window_min: int = WS_WINDOW_MIN,
    min_support: int = WS_MIN_SUPPORT,
    min_share: float = WS_MIN_SHARE,
) -> pd.DataFrame:
    """Infer each workstation room from nearby flowsheet rooms for the same staff."""
    fs_rooms = load_flowsheet_rooms(con)
    if not fs_rooms:
        raise RuntimeError(
            "No flowsheet room mappings were available from Ref.Department."
        )

    ws_names = load_ref_map(con, *SOURCE_REF["Workstation"])
    rows = con.execute(
        """
        select
            cast(e.MasterIndexId as varchar) as staff,
            epoch(e.EventDateTime) as ts,
            e.SourceKey,
            it.InteractionTypeClass
        from Data.StaffLocationEvent e
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        where it.InteractionTypeClass in ('Workstation', 'Flowsheet')
          and e.SourceKey is not null
        order by e.MasterIndexId, e.EventDateTime
        """
    ).fetchall()

    window = window_min * 60.0
    votes: dict[int, Counter[str]] = defaultdict(Counter)

    current_staff: str | None = None
    staff_events: list[tuple[float, int, str]] = []

    def process_staff(events: list[tuple[float, int, str]]) -> None:
        if not events:
            return
        flowsheets = [
            (ts, fs_rooms[source_key])
            for ts, source_key, iclass in events
            if iclass == "Flowsheet" and source_key in fs_rooms
        ]
        if not flowsheets:
            return
        low = 0
        for ts, source_key, iclass in events:
            if iclass != "Workstation":
                continue
            while low < len(flowsheets) and flowsheets[low][0] < ts - window:
                low += 1
            j = low
            while j < len(flowsheets) and flowsheets[j][0] <= ts + window:
                votes[source_key][flowsheets[j][1]] += 1
                j += 1

    for staff, ts, source_key, iclass in rows:
        staff = str(staff)
        if current_staff is None:
            current_staff = staff
        if staff != current_staff:
            process_staff(staff_events)
            staff_events = []
            current_staff = staff
        staff_events.append((float(ts), int(source_key), str(iclass)))
    process_staff(staff_events)

    records: list[dict[str, Any]] = []
    for source_key in sorted(ws_names):
        counts = votes.get(source_key, Counter())
        support = int(sum(counts.values()))
        if support == 0:
            records.append(
                {
                    "iclass": "Workstation",
                    "source_key": source_key,
                    "name_hint": ws_names[source_key],
                    "room": "",
                    "support": 0,
                    "share": np.nan,
                    "runner_up": "",
                }
            )
            continue

        ranked = counts.most_common(2)
        best_room, best_count = ranked[0]
        runner_up = ranked[1][0].removeprefix("room:") if len(ranked) > 1 else ""
        share = best_count / support
        confident = support >= min_support and share >= min_share
        records.append(
            {
                "iclass": "Workstation",
                "source_key": source_key,
                "name_hint": ws_names[source_key],
                "room": best_room.removeprefix("room:") if confident else "",
                "support": support,
                "share": round(share, 4),
                "runner_up": runner_up,
            }
        )

    frame = pd.DataFrame.from_records(records)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_path, index=False)
    return frame


def load_or_create_crosswalk(
    con: duckdb.DuckDBPyConnection,
    crosswalk_path: Path,
    refresh: bool,
    window_min: int,
    min_support: int,
    min_share: float,
) -> tuple[pd.DataFrame, str]:
    if crosswalk_path.exists() and not refresh:
        frame = pd.read_csv(crosswalk_path)
        return frame, "existing"
    frame = infer_workstation_crosswalk(
        con=con,
        out_path=crosswalk_path,
        window_min=window_min,
        min_support=min_support,
        min_share=min_share,
    )
    return frame, "generated"


def workstation_room_map(crosswalk: pd.DataFrame) -> dict[int, str]:
    if crosswalk.empty:
        return {}
    needed = {"source_key", "room"}
    if not needed.issubset(crosswalk.columns):
        raise RuntimeError(
            f"Crosswalk lacks required columns {sorted(needed)}; found {list(crosswalk.columns)}"
        )
    out: dict[int, str] = {}
    for _, row in crosswalk.iterrows():
        room = row.get("room")
        if pd.isna(room) or not str(room).strip():
            continue
        out[int(row["source_key"])] = f"room:{std_code(str(room))}"
    return out


def event_summary(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    row = con.execute(
        """
        select
            count(*) as total_events,
            count(distinct MasterIndexId) as staff_agents,
            min(EventDateTime) as first_event,
            max(EventDateTime) as last_event
        from Data.StaffLocationEvent
        """
    ).df()
    return row


def valid_roster_shifts(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Create valid roster intervals and count non-roster events in each interval."""
    # min(start)/max(end) per pair, in case of duplicate roster records.
    query = """
    with roster_pairs as (
        select
            cast(e.MasterIndexId as varchar) as staff,
            cast(e.LinkKey as bigint) as LinkKey,
            min(case when it.InteractionType = 'Roster Start' then e.EventDateTime end)
                as shift_start,
            max(case when it.InteractionType = 'Roster End' then e.EventDateTime end)
                as shift_end,
            max(case when it.InteractionType = 'Roster Start' then e.SourceKey end)
                as roster_key,
            count(*) filter (where it.InteractionType = 'Roster Start') as start_records,
            count(*) filter (where it.InteractionType = 'Roster End') as end_records
        from Data.StaffLocationEvent e
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        where it.InteractionTypeClass = 'Roster'
          and e.LinkKey is not null
        group by e.MasterIndexId, e.LinkKey
    ), valid as (
        select
            p.*,
            coalesce(r.RosterName, 'unknown') as roster_unit,
            (epoch(p.shift_end) - epoch(p.shift_start)) / 3600.0 as duration_hours
        from roster_pairs p
        left join Ref.Roster r
          on p.roster_key = r.RosterKey
        where p.shift_start is not null
          and p.shift_end is not null
          and p.shift_end > p.shift_start
    )
    select
        v.staff,
        v.LinkKey,
        v.shift_start,
        v.shift_end,
        v.roster_key,
        v.roster_unit,
        v.duration_hours,
        v.start_records,
        v.end_records,
        count(e.EventDateTime) filter (
            where it2.InteractionTypeClass <> 'Roster'
        ) as activity_events
    from valid v
    left join Data.StaffLocationEvent e
      on cast(e.MasterIndexId as varchar) = v.staff
     and e.EventDateTime between v.shift_start and v.shift_end
    left join Ref.InteractionType it2
      on e.InteractionTypeKey = it2.InteractionTypeKey
    group by
        v.staff,
        v.LinkKey,
        v.shift_start,
        v.shift_end,
        v.roster_key,
        v.roster_unit,
        v.duration_hours,
        v.start_records,
        v.end_records
    order by v.shift_start
    """
    return con.execute(query).df()


def roster_unit_summary(shifts: pd.DataFrame) -> pd.DataFrame:
    if shifts.empty:
        return pd.DataFrame(
            columns=[
                "roster_unit",
                "shifts",
                "staff",
                "median_hours",
                "minimum_hours",
                "maximum_hours",
                "median_activity_events",
            ]
        )
    result = (
        shifts.groupby("roster_unit", dropna=False)
        .agg(
            shifts=("LinkKey", "count"),
            staff=("staff", "nunique"),
            median_hours=("duration_hours", "median"),
            minimum_hours=("duration_hours", "min"),
            maximum_hours=("duration_hours", "max"),
            median_activity_events=("activity_events", "median"),
        )
        .reset_index()
    )
    for col in [
        "median_hours",
        "minimum_hours",
        "maximum_hours",
        "median_activity_events",
    ]:
        result[col] = result[col].round(2)
    return result.sort_values("shifts", ascending=False).reset_index(drop=True)


def build_overall_summary(
    events: pd.DataFrame,
    shifts: pd.DataFrame,
    unit_summary: pd.DataFrame,
) -> pd.DataFrame:
    e = events.iloc[0]
    valid = shifts[shifts["activity_events"] >= 3].copy()
    return pd.DataFrame(
        [
            {
                "metric": "Total events",
                "value": int(e["total_events"]),
            },
            {
                "metric": "Staff / agents in event data",
                "value": int(e["staff_agents"]),
            },
            {
                "metric": "Valid roster intervals",
                "value": int(len(shifts)),
            },
            {
                "metric": "Shifts with at least 3 activity events",
                "value": int(len(valid)),
            },
            {
                "metric": "Roster units",
                "value": int(unit_summary["roster_unit"].nunique())
                if not unit_summary.empty
                else 0,
            },
            {
                "metric": "Median shift length (hours)",
                "value": round(float(shifts["duration_hours"].median()), 2)
                if not shifts.empty
                else np.nan,
            },
            {
                "metric": "First event",
                "value": str(e["first_event"]),
            },
            {
                "metric": "Last event",
                "value": str(e["last_event"]),
            },
        ]
    )


def door_report(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    event_counts = con.execute(
        """
        select
            e.SourceKey as DoorKey,
            count(*) as event_count
        from Data.StaffLocationEvent e
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        where it.InteractionTypeClass = 'Door Message'
        group by e.SourceKey
        """
    ).df()

    doors = con.execute("select DoorKey, DoorName from Ref.Door order by DoorKey").df()
    names = {
        int(row.DoorKey): str(row.DoorName) for row in doors.itertuples(index=False)
    }
    parsed = parse_door_points(names)
    doors["parsed_location"] = doors["DoorKey"].astype(int).map(parsed)
    doors["status"] = np.where(
        doors["parsed_location"].notna(),
        "identified",
        "unresolved",
    )
    doors = doors.merge(event_counts, on="DoorKey", how="left")
    doors["event_count"] = doors["event_count"].fillna(0).astype(int)
    return doors[["DoorKey", "DoorName", "parsed_location", "event_count", "status"]]


def workstation_report(
    con: duckdb.DuckDBPyConnection,
    crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    counts = con.execute(
        """
        select
            e.SourceKey as source_key,
            count(*) as event_count
        from Data.StaffLocationEvent e
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        where it.InteractionTypeClass = 'Workstation'
        group by e.SourceKey
        """
    ).df()

    frame = crosswalk.copy()
    for column in ["source_key", "name_hint", "room", "support", "share", "runner_up"]:
        if column not in frame.columns:
            frame[column] = np.nan
    frame["source_key"] = pd.to_numeric(frame["source_key"], errors="coerce").astype(
        "Int64"
    )
    counts["source_key"] = pd.to_numeric(counts["source_key"], errors="coerce").astype(
        "Int64"
    )
    frame = frame.merge(counts, on="source_key", how="left")
    frame["event_count"] = frame["event_count"].fillna(0).astype(int)
    frame["status"] = np.where(
        frame["room"].notna() & frame["room"].astype(str).str.strip().ne(""),
        "placed",
        "unresolved / possibly mobile",
    )
    frame["share"] = pd.to_numeric(frame["share"], errors="coerce")
    frame["support"] = (
        pd.to_numeric(frame["support"], errors="coerce").fillna(0).astype(int)
    )
    return frame[
        [
            "source_key",
            "name_hint",
            "room",
            "support",
            "share",
            "runner_up",
            "event_count",
            "status",
        ]
    ].sort_values(["status", "share"], ascending=[True, False], na_position="last")


def mapping_coverage(
    con: duckdb.DuckDBPyConnection,
    flowsheet_map: dict[int, str],
    door_map: dict[int, str],
    workstation_map: dict[int, str],
) -> pd.DataFrame:
    rows = con.execute(
        """
        select
            it.InteractionTypeClass as iclass,
            count(*) as event_count,
            count(distinct e.SourceKey) as distinct_source_keys,
            count(*) filter (where e.SourceKey is null) as null_source_events
        from Data.StaffLocationEvent e
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        where it.InteractionTypeClass in ('Flowsheet', 'Door Message', 'Workstation')
        group by it.InteractionTypeClass
        order by it.InteractionTypeClass
        """
    ).df()

    map_by_class = {
        "Flowsheet": flowsheet_map,
        "Door Message": door_map,
        "Workstation": workstation_map,
    }

    used_keys = con.execute(
        """
        select distinct
            it.InteractionTypeClass as iclass,
            e.SourceKey
        from Data.StaffLocationEvent e
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        where it.InteractionTypeClass in ('Flowsheet', 'Door Message', 'Workstation')
          and e.SourceKey is not null
        """
    ).fetchall()
    used_by_class: dict[str, set[int]] = defaultdict(set)
    for iclass, source_key in used_keys:
        used_by_class[str(iclass)].add(int(source_key))

    output: list[dict[str, Any]] = []
    for row in rows.itertuples(index=False):
        iclass = str(row.iclass)
        mapped_used = len(used_by_class[iclass] & set(map_by_class[iclass]))
        distinct_keys = int(row.distinct_source_keys)
        output.append(
            {
                "event_class": iclass,
                "event_count": int(row.event_count),
                "distinct_source_keys": distinct_keys,
                "mapped_used_source_keys": mapped_used,
                "unmapped_used_source_keys": max(0, distinct_keys - mapped_used),
                "key_mapping_percent": round(100 * mapped_used / distinct_keys, 1)
                if distinct_keys
                else 0.0,
                "null_source_events": int(row.null_source_events),
            }
        )
    return pd.DataFrame(output)


def choose_example_shift(
    shifts: pd.DataFrame, target_events: int = 12
) -> ValidShift | None:
    candidates = shifts[shifts["activity_events"] >= 3].copy()
    if candidates.empty:
        return None
    candidates["distance"] = (candidates["activity_events"] - target_events).abs()
    row = candidates.sort_values(["distance", "activity_events", "shift_start"]).iloc[0]
    roster_key = None if pd.isna(row["roster_key"]) else int(row["roster_key"])
    return ValidShift(
        staff=str(row["staff"]),
        link_key=int(row["LinkKey"]),
        shift_start=row["shift_start"],
        shift_end=row["shift_end"],
        roster_key=roster_key,
        roster_unit=str(row["roster_unit"]),
        activity_events=int(row["activity_events"]),
    )


def resolve_location(
    iclass: str,
    source_key: Any,
    room_maps: dict[str, dict[int, str]],
    fallback_maps: dict[str, dict[int, str]],
) -> tuple[str, str]:
    prefix = CLASS_PREFIX.get(iclass, "x")
    if source_key is None or (isinstance(source_key, float) and math.isnan(source_key)):
        return f"{prefix}:na", "null"
    key = int(source_key)
    mapped = room_maps.get(iclass, {}).get(key)
    if mapped is not None:
        if mapped.startswith("room:"):
            return mapped, "room"
        if mapped.startswith("doorpoint:"):
            return mapped, "doorpoint"
        return mapped, "mapped"
    name = fallback_maps.get(iclass, {}).get(key)
    return f"{prefix}:{name if name is not None else key}", "fallback"


def example_sequence(
    con: duckdb.DuckDBPyConnection,
    chosen: ValidShift | None,
    flowsheet_map: dict[int, str],
    door_map: dict[int, str],
    workstation_map: dict[int, str],
) -> pd.DataFrame:
    columns = [
        "step",
        "time_UTC",
        "location",
        "resolution",
        "event_class",
        "event_type",
        "role",
        "roster_unit",
    ]
    if chosen is None:
        return pd.DataFrame(columns=columns)

    staff_cols = table_columns(con, "Ref", "Staff")
    role_expression = (
        "coalesce(cast(s.Role as varchar), 'unknown')"
        if "Role" in staff_cols
        else "'unknown'"
    )

    query = f"""
        select
            e.EventDateTime,
            e.SourceKey,
            it.InteractionType,
            it.InteractionTypeClass,
            {role_expression} as role
        from Data.StaffLocationEvent e
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        left join Ref.Staff s
          on s.MasterIndexId = e.MasterIndexId
        where cast(e.MasterIndexId as varchar) = ?
          and e.EventDateTime between ? and ?
          and it.InteractionTypeClass <> 'Roster'
        order by e.EventDateTime
    """
    raw = con.execute(
        query,
        [chosen.staff, chosen.shift_start, chosen.shift_end],
    ).df()

    fallback_maps = {
        iclass: load_ref_map(con, *spec)
        for iclass, spec in SOURCE_REF.items()
        if iclass != "Roster"
    }
    room_maps = {
        "Flowsheet": flowsheet_map,
        "Door Message": door_map,
        "Workstation": workstation_map,
    }

    records: list[dict[str, Any]] = []
    for index, row in enumerate(raw.itertuples(index=False), start=1):
        location, resolution = resolve_location(
            iclass=str(row.InteractionTypeClass),
            source_key=row.SourceKey,
            room_maps=room_maps,
            fallback_maps=fallback_maps,
        )
        timestamp = pd.Timestamp(row.EventDateTime)
        records.append(
            {
                "step": index,
                "time_UTC": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "location": location,
                "resolution": resolution,
                "event_class": str(row.InteractionTypeClass),
                "event_type": str(row.InteractionType),
                "role": str(row.role),
                "roster_unit": chosen.roster_unit,
            }
        )
    return pd.DataFrame.from_records(records, columns=columns)


def format_cell(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    if isinstance(value, (np.integer, int)):
        return f"{int(value):,}"
    if isinstance(value, (np.floating, float)):
        return f"{float(value):,.2f}"
    return str(value)


def save_table_png(
    frame: pd.DataFrame,
    title: str,
    path: Path,
    max_rows: int = 40,
    note: str | None = None,
) -> None:
    display_frame = frame.head(max_rows).copy()
    if display_frame.empty:
        display_frame = pd.DataFrame({"message": ["No rows available"]})

    n_rows, n_cols = display_frame.shape
    fig_width = max(9.0, min(22.0, 2.0 + n_cols * 2.2))
    fig_height = max(2.8, min(24.0, 1.7 + n_rows * 0.43))

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis("off")
    ax.set_title(title, fontsize=16, pad=16)

    cell_text = [
        [format_cell(value) for value in row]
        for row in display_frame.itertuples(index=False, name=None)
    ]
    table = ax.table(
        cellText=cell_text,
        colLabels=[str(c) for c in display_frame.columns],
        cellLoc="left",
        colLoc="left",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1, 1.25)
    try:
        table.auto_set_column_width(col=list(range(n_cols)))
    except Exception:
        pass

    footer_parts: list[str] = []
    if len(frame) > max_rows:
        footer_parts.append(f"Showing first {max_rows} of {len(frame)} rows")
    if note:
        footer_parts.append(note)
    if footer_parts:
        fig.text(0.01, 0.01, " | ".join(footer_parts), fontsize=8)

    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_bar_png(
    frame: pd.DataFrame,
    category_col: str,
    value_col: str,
    title: str,
    path: Path,
    xlabel: str,
) -> None:
    plot_frame = frame.copy()
    if plot_frame.empty:
        save_table_png(pd.DataFrame({"message": ["No data available"]}), title, path)
        return
    plot_frame = plot_frame.sort_values(value_col, ascending=True)
    fig_height = max(4.0, min(14.0, 1.5 + len(plot_frame) * 0.55))
    fig, ax = plt.subplots(figsize=(10, fig_height))
    ax.barh(plot_frame[category_col].astype(str), plot_frame[value_col].astype(float))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("")
    for index, value in enumerate(plot_frame[value_col].astype(float)):
        ax.text(value, index, f" {value:,.0f}", va="center")
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_mapping_coverage_png(frame: pd.DataFrame, path: Path) -> None:
    if frame.empty:
        save_table_png(
            pd.DataFrame({"message": ["No mapping data available"]}),
            "Location-key mapping coverage",
            path,
        )
        return
    plot_frame = frame.copy().sort_values("key_mapping_percent")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(plot_frame["event_class"], plot_frame["key_mapping_percent"])
    ax.set_title("Used location keys successfully mapped")
    ax.set_xlabel("Mapped distinct SourceKeys (%)")
    ax.set_xlim(0, 100)
    ax.set_ylabel("")
    for index, row in enumerate(plot_frame.itertuples(index=False)):
        ax.text(
            float(row.key_mapping_percent),
            index,
            f" {row.mapped_used_source_keys}/{row.distinct_source_keys} ({row.key_mapping_percent:.1f}%)",
            va="center",
        )
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def short_location(value: str, max_len: int = 30) -> str:
    value = str(value)
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def save_sequence_png(
    sequence: pd.DataFrame,
    path: Path,
    max_steps: int = 15,
) -> None:
    if sequence.empty:
        save_table_png(
            pd.DataFrame({"message": ["No example sequence available"]}),
            "Example rostered activity sequence",
            path,
        )
        return

    shown = sequence.head(max_steps).copy()
    n = len(shown)
    fig_width = max(12.0, n * 2.2)
    fig, ax = plt.subplots(figsize=(fig_width, 4.8))
    ax.axis("off")
    ax.set_title(
        "Example rostered activity sequence (identifiers removed)", fontsize=16, pad=18
    )

    xs = np.arange(n) * 2.0
    y = 0.5
    for i, row in enumerate(shown.itertuples(index=False)):
        label = (
            f"{row.time_UTC[-8:]}\n"
            f"{short_location(row.location, 28)}\n"
            f"{row.event_class}"
        )
        ax.text(
            xs[i],
            y,
            label,
            ha="center",
            va="center",
            fontsize=8,
            bbox={
                "boxstyle": "round,pad=0.45",
                "facecolor": "white",
                "edgecolor": "black",
            },
        )
        if i < n - 1:
            ax.annotate(
                "",
                xy=(xs[i + 1] - 0.55, y),
                xytext=(xs[i] + 0.55, y),
                arrowprops={"arrowstyle": "->"},
            )

    ax.set_xlim(-1.2, xs[-1] + 1.2)
    ax.set_ylim(-0.8, 1.6)
    if len(sequence) > max_steps:
        ax.text(
            xs[-1] + 0.8,
            y,
            f"…\n{len(sequence) - max_steps} more steps",
            ha="left",
            va="center",
            fontsize=9,
        )
    unit = str(sequence.iloc[0]["roster_unit"])
    fig.text(
        0.01,
        0.02,
        f"Roster unit: {unit} | Total activity steps in selected shift: {len(sequence)}",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False)


def write_index(
    path: Path,
    db_path: Path,
    crosswalk_state: str,
    crosswalk_path: Path,
    generated_files: Iterable[Path],
) -> None:
    lines = [
        "AMR-HUB progress report",
        "=======================",
        f"Database: {db_path}",
        f"Crosswalk: {crosswalk_path} ({crosswalk_state})",
        "",
        "Generated files:",
    ]
    lines.extend(f"- {p.name}" for p in generated_files)
    lines.extend(
        [
            "",
            "Notes:",
            "- No staff or patient IDs.",
            "- Door points do not give direction of travel.",
            "- Blank workstation rooms are unresolved.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_report(args: argparse.Namespace) -> Path:
    db_path = find_database(args.db)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    crosswalk_path = Path(args.crosswalk).resolve()

    print(f"Database: {db_path}")
    print(f"Output directory: {output_dir}")
    print("Opening in-memory DuckDB connection and attaching database as 'output'...")
    con = connect_database(db_path, catalog_alias="output")
    try:
        require_tables(con)

        print("Loading or generating workstation crosswalk...")
        crosswalk, crosswalk_state = load_or_create_crosswalk(
            con=con,
            crosswalk_path=crosswalk_path,
            refresh=args.refresh_crosswalk,
            window_min=args.window_min,
            min_support=args.min_support,
            min_share=args.min_share,
        )
        workstation_map = workstation_room_map(crosswalk)
        flowsheet_map = load_flowsheet_rooms(con)
        door_names = load_ref_map(con, *SOURCE_REF["Door Message"])
        door_map = parse_door_points(door_names)

        print("Computing summaries...")
        events = event_summary(con)
        shifts = valid_roster_shifts(con)
        units = roster_unit_summary(shifts)
        overall = build_overall_summary(events, shifts, units)
        doors = door_report(con)
        workstations = workstation_report(con, crosswalk)
        coverage = mapping_coverage(
            con=con,
            flowsheet_map=flowsheet_map,
            door_map=door_map,
            workstation_map=workstation_map,
        )
        chosen = choose_example_shift(shifts, target_events=args.example_target_length)
        sequence = example_sequence(
            con=con,
            chosen=chosen,
            flowsheet_map=flowsheet_map,
            door_map=door_map,
            workstation_map=workstation_map,
        )

        placed = workstations[workstations["status"] == "placed"].copy()
        unresolved = workstations[workstations["status"] != "placed"].copy()
        status_counts = (
            workstations.groupby("status").size().reset_index(name="workstations")
        )

        generated: list[Path] = []

        csv_outputs = {
            "overall_summary.csv": overall,
            "roster_units.csv": units,
            "doors.csv": doors,
            "workstations.csv": workstations,
            "mapping_coverage.csv": coverage,
            "example_sequence.csv": sequence,
        }
        for filename, frame in csv_outputs.items():
            path = output_dir / filename
            save_csv(frame, path)
            generated.append(path)

        path = output_dir / "01_overall_summary.png"
        save_table_png(
            overall,
            "AMR-HUB data and roster summary",
            path,
            note="Aggregate counts.",
        )
        generated.append(path)

        path = output_dir / "02_roster_unit_counts.png"
        save_bar_png(
            units,
            category_col="roster_unit",
            value_col="shifts",
            title="Valid roster intervals by unit",
            path=path,
            xlabel="Number of roster intervals",
        )
        generated.append(path)

        path = output_dir / "03_roster_unit_durations.png"
        save_table_png(
            units,
            "Roster-unit shift duration summary",
            path,
            note="From paired Roster Start/End records.",
        )
        generated.append(path)

        path = output_dir / "04_doors_identified.png"
        save_table_png(
            doors,
            "Door points identified from Ref.Door",
            path,
            max_rows=30,
            note="Door points do not give direction of travel.",
        )
        generated.append(path)

        path = output_dir / "05_workstation_status.png"
        save_bar_png(
            status_counts,
            category_col="status",
            value_col="workstations",
            title="Workstation room-placement status",
            path=path,
            xlabel="Number of workstations",
        )
        generated.append(path)

        path = output_dir / "06_workstations_placed.png"
        save_table_png(
            placed,
            "Workstations confidently placed in rooms",
            path,
            max_rows=40,
            note=f"Support ≥ {args.min_support}, share ≥ {args.min_share:.2f}.",
        )
        generated.append(path)

        path = output_dir / "07_workstations_unresolved.png"
        save_table_png(
            unresolved,
            "Workstations left unresolved / possibly mobile",
            path,
            max_rows=40,
            note="Blank rooms are unresolved.",
        )
        generated.append(path)

        path = output_dir / "08_mapping_coverage.png"
        save_mapping_coverage_png(coverage, path)
        generated.append(path)

        path = output_dir / "09_example_sequence.png"
        save_sequence_png(sequence, path, max_steps=args.max_sequence_steps)
        generated.append(path)

        index_path = output_dir / "REPORT_INDEX.txt"
        write_index(
            index_path,
            db_path=db_path,
            crosswalk_state=crosswalk_state,
            crosswalk_path=crosswalk_path,
            generated_files=generated,
        )
        generated.append(index_path)

        print("\nReport complete. Generated:")
        for path in generated:
            print(f"  {path}")
        return output_dir
    finally:
        con.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate AMR-HUB progress-report PNGs and CSVs from DuckDB."
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Database path or filename under /data. If omitted, the sole .db/.duckdb in /data is used.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for report files (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--crosswalk",
        default=str(DEFAULT_CROSSWALK),
        help=f"Workstation crosswalk path (default: {DEFAULT_CROSSWALK}).",
    )
    parser.add_argument(
        "--refresh-crosswalk",
        action="store_true",
        help="Regenerate and overwrite the workstation crosswalk instead of using an existing one.",
    )
    parser.add_argument("--window-min", type=int, default=WS_WINDOW_MIN)
    parser.add_argument("--min-support", type=int, default=WS_MIN_SUPPORT)
    parser.add_argument("--min-share", type=float, default=WS_MIN_SHARE)
    parser.add_argument(
        "--example-target-length",
        type=int,
        default=12,
        help="Choose an example shift with an activity-event count close to this value.",
    )
    parser.add_argument(
        "--max-sequence-steps",
        type=int,
        default=15,
        help="Maximum number of steps drawn in the sequence PNG.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        generate_report(args)
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
