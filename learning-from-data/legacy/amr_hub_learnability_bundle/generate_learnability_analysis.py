#!/usr/bin/env python3
"""Build the canonical rostered event table and run held-out learnability tests.

Locations: Flowsheet via Ref.Department.RoomName, Workstation via ws_crosswalk.csv,
Door Message as door point (code + DoorKey). Unresolved events are kept with a null
location. Train/test split is by whole shift.
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import random
import re
from collections import Counter
from pathlib import Path

import duckdb


DOOR_CODE_RE = re.compile(r"\b(?:E\d{2})?[A-Z]{2}\d{2,3}[A-Z]?\b", re.IGNORECASE)
DEFAULT_TRAIN_FRACTION = 0.80
DEFAULT_SEED = 20260813
DEFAULT_MIN_GROUP_SHIFTS = 30
DEFAULT_MIN_GROUP_TEST_PAIRS = 100


def std_code(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def sql_quote(value: str | Path) -> str:
    return str(value).replace("'", "''")


def find_database(db_arg: str | None) -> Path:
    if db_arg:
        p = Path(db_arg)
        if not p.is_absolute():
            p = Path("/data") / p
        if not p.exists():
            raise SystemExit(f"Database not found: {p}")
        return p

    candidates: list[Path] = []
    for pattern in ("*.duckdb", "*.db", "*.ddb"):
        candidates.extend(Path("/data").glob(pattern))
    candidates = sorted({p.resolve() for p in candidates if p.is_file()})
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise SystemExit("No .duckdb/.db/.ddb file found in /data. Use --db FILENAME.")
    names = "\n  ".join(p.name for p in candidates)
    raise SystemExit(f"Multiple database files found. Use --db FILENAME.\n  {names}")


def connect_database(db_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{sql_quote(db_path)}' AS output (READ_ONLY)")
    con.execute("USE output")
    return con


def load_crosswalk(path: Path | None) -> dict[int, str]:
    if path is None or not path.exists():
        return {}
    out: dict[int, str] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = {str(x).strip().lower() for x in (reader.fieldnames or [])}
        if not {"source_key", "room"}.issubset(fields):
            print(f"[crosswalk] {path} lacks source_key/room; ignored")
            return {}
        for row in reader:
            norm = {str(k).strip().lower(): v for k, v in row.items()}
            if (
                "iclass" in norm
                and str(norm.get("iclass", "")).strip() != "Workstation"
            ):
                continue
            room = str(norm.get("room") or "").strip()
            key = str(norm.get("source_key") or "").strip()
            if not room or not key:
                continue
            try:
                out[int(float(key))] = f"room:{std_code(room)}"
            except ValueError:
                continue
    print(f"[crosswalk] {len(out)} workstation mappings loaded from {path}")
    return out


def create_location_map(
    con: duckdb.DuckDBPyConnection, crosswalk: Path | None
) -> list[tuple[str, int, str, str]]:
    records: list[tuple[str, int, str, str]] = []

    try:
        rows = con.execute("""
            select DepartmentKey, RoomName
            from Ref.Department
            where DepartmentKey is not null and RoomName is not null
        """).fetchall()
        for key, room in rows:
            records.append(("Flowsheet", int(key), f"room:{std_code(room)}", "room"))
        print(f"[locations] {len(rows)} flowsheet/department rows available")
    except duckdb.Error as exc:
        print(f"[locations] WARNING: could not read Ref.Department: {exc}")

    for key, loc in load_crosswalk(crosswalk).items():
        records.append(("Workstation", int(key), loc, "room"))

    # DoorKey suffix keeps doors that share a parsed code distinct.
    try:
        rows = con.execute("""
            select DoorKey, DoorName
            from Ref.Door
            where DoorKey is not null and DoorName is not null
        """).fetchall()
        n = 0
        for key, name in rows:
            m = DOOR_CODE_RE.search(std_code(name))
            if m is None:
                continue
            code = m.group(0).upper()
            records.append(
                (
                    "Door Message",
                    int(key),
                    f"doorpoint:{code}#DOORKEY:{int(key)}",
                    "doorpoint",
                )
            )
            n += 1
        print(f"[locations] {n}/{len(rows)} doors received a door-point code")
    except duckdb.Error as exc:
        print(f"[locations] WARNING: could not read Ref.Door: {exc}")

    # Last mapping wins for duplicate class/key.
    dedup: dict[tuple[str, int], tuple[str, int, str, str]] = {}
    for rec in records:
        dedup[(rec[0], rec[1])] = rec
    records = list(dedup.values())

    con.execute("""
        create or replace temp table location_map (
            iclass varchar,
            source_key bigint,
            resolved_location varchar,
            mapping_type varchar
        )
    """)
    if records:
        con.executemany("insert into location_map values (?, ?, ?, ?)", records)
    return records


def create_canonical_tables(
    con: duckdb.DuckDBPyConnection,
) -> dict[str, float]:
    print("[sql] building roster intervals ...")
    con.execute("""
        create or replace temp table roster_intervals_raw as
        with paired as (
            select
                cast(e.MasterIndexId as varchar) as staff_raw,
                cast(e.LinkKey as bigint) as link_key,
                max(case when it.InteractionType = 'Roster Start' then e.EventDateTime end) as shift_start,
                max(case when it.InteractionType = 'Roster End' then e.EventDateTime end) as shift_end,
                max(case when it.InteractionType = 'Roster Start' then e.SourceKey end) as roster_key
            from Data.StaffLocationEvent e
            join Ref.InteractionType it
              on e.InteractionTypeKey = it.InteractionTypeKey
            where it.InteractionTypeClass = 'Roster'
              and e.LinkKey is not null
            group by e.MasterIndexId, e.LinkKey
        )
        select
            p.*,
            coalesce(r.RosterName, 'unknown') as roster_unit,
            (epoch(p.shift_end) - epoch(p.shift_start)) / 3600.0 as shift_duration_hours
        from paired p
        left join Ref.Roster r
          on p.roster_key = r.RosterKey
        where p.shift_start is not null
          and p.shift_end is not null
          and p.shift_end > p.shift_start
    """)

    con.execute("""
        create or replace temp table staff_map as
        select
            staff_raw,
            row_number() over(order by staff_raw) as staff_id
        from (select distinct staff_raw from roster_intervals_raw)
    """)

    con.execute("""
        create or replace temp table roster_intervals as
        select
            row_number() over(order by r.staff_raw, r.shift_start, r.link_key) as shift_id,
            s.staff_id,
            r.staff_raw,
            r.link_key,
            r.shift_start,
            r.shift_end,
            r.roster_unit,
            r.shift_duration_hours
        from roster_intervals_raw r
        join staff_map s using(staff_raw)
    """)

    overlap_count = int(
        con.execute("""
        with x as (
            select
                staff_raw,
                shift_start,
                shift_end,
                lag(shift_end) over(partition by staff_raw order by shift_start, shift_end) as prev_end
            from roster_intervals
        )
        select count(*) from x
        where prev_end is not null and shift_start <= prev_end
    """).fetchone()[0]
    )
    print(f"[quality] overlapping roster intervals: {overlap_count}")

    print("[sql] building non-roster event stream ...")
    con.execute("""
        create or replace temp table base_activity_events as
        select
            row_number() over(
                order by cast(e.MasterIndexId as varchar), e.EventDateTime,
                         e.InteractionTypeKey, e.SourceKey
            ) as event_uid,
            cast(e.MasterIndexId as varchar) as staff_raw,
            e.EventDateTime as event_time,
            e.SourceKey as source_key,
            it.InteractionType as itype,
            it.InteractionTypeClass as iclass,
            coalesce(s.Role, 'unknown') as role,
            case when e.PatientDurableKey is null then false else true end as has_patient
        from Data.StaffLocationEvent e
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        left join Ref.Staff s
          on s.MasterIndexId = e.MasterIndexId
        where it.InteractionTypeClass <> 'Roster'
    """)

    multi_candidate_events = int(
        con.execute("""
        with candidates as (
            select e.event_uid, count(*) as n
            from base_activity_events e
            join roster_intervals r
              on e.staff_raw = r.staff_raw
             and e.event_time between r.shift_start and r.shift_end
            group by e.event_uid
        )
        select count(*) from candidates where n > 1
    """).fetchone()[0]
    )
    print(
        f"[quality] activity events matching >1 roster interval: {multi_candidate_events}"
    )

    # Overlapping intervals: assign each event to the candidate with the latest start.
    con.execute("""
        create or replace temp table activity_assigned as
        select * exclude(candidate_rank)
        from (
            select
                r.shift_id,
                r.staff_id,
                r.link_key,
                r.shift_start,
                r.shift_end,
                r.shift_duration_hours,
                r.roster_unit,
                e.event_uid,
                e.event_time,
                e.source_key,
                e.itype,
                e.iclass,
                e.role,
                e.has_patient,
                row_number() over(
                    partition by e.event_uid
                    order by r.shift_start desc, r.shift_id desc
                ) as candidate_rank
            from base_activity_events e
            join roster_intervals r
              on e.staff_raw = r.staff_raw
             and e.event_time between r.shift_start and r.shift_end
        )
        where candidate_rank = 1
    """)

    print("[sql] applying spatial mapping and constructing canonical sequence ...")
    con.execute("""
        create or replace temp table canonical_events_internal as
        select
            a.shift_id,
            a.staff_id,
            row_number() over(
                partition by a.shift_id order by a.event_time, a.event_uid
            ) as event_index,
            a.event_time,
            (epoch(a.event_time) - epoch(a.shift_start)) / 60.0 as minutes_from_shift_start,
            cast(extract(hour from a.event_time) as integer) as hour_of_day,
            cast(floor(extract(hour from a.event_time) / 6) as integer) as time_bucket,
            strftime(a.event_time, '%a') as weekday,
            a.shift_duration_hours,
            a.roster_unit,
            a.role,
            a.iclass as interaction_class,
            a.itype as interaction_type,
            a.source_key,
            a.has_patient,
            lm.resolved_location,
            lm.mapping_type,
            case when lm.resolved_location is not null then true else false end as location_resolved,
            case when lm.resolved_location like 'room:%' then true else false end as room_resolved,
            case when lm.resolved_location like 'doorpoint:%' then true else false end as doorpoint_resolved
        from activity_assigned a
        left join location_map lm
          on lm.iclass = a.iclass
         and lm.source_key = cast(a.source_key as bigint)
    """)

    con.execute("""
        create or replace temp table class_pairs as
        with x as (
            select
                shift_id, staff_id, event_index,
                interaction_class as current_class,
                interaction_type as current_itype,
                lag(interaction_class) over(partition by shift_id order by event_index) as prev_class,
                lead(interaction_class) over(partition by shift_id order by event_index) as action,
                time_bucket, role, roster_unit
            from canonical_events_internal
        )
        select * from x where action is not null
    """)

    # Room-resolved observations only; door points and unresolved events are excluded.
    con.execute("""
        create or replace temp table room_observation_pairs as
        with room_seq as (
            select
                shift_id, staff_id, event_index,
                resolved_location as current_room,
                interaction_class as current_class,
                interaction_type as current_itype,
                lag(resolved_location) over(partition by shift_id order by event_index) as prev_room,
                lead(resolved_location) over(partition by shift_id order by event_index) as action,
                time_bucket, role, roster_unit
            from canonical_events_internal
            where room_resolved
        )
        select * from room_seq where action is not null
    """)

    # Collapse consecutive repeats of the same room before forming pairs.
    con.execute("""
        create or replace temp table room_change_pairs as
        with room_obs as (
            select
                shift_id, staff_id, event_index,
                resolved_location as current_room,
                interaction_class as current_class,
                interaction_type as current_itype,
                time_bucket, role, roster_unit,
                lag(resolved_location) over(partition by shift_id order by event_index) as immediate_prev_room
            from canonical_events_internal
            where room_resolved
        ),
        runs as (
            select * from room_obs
            where immediate_prev_room is null or current_room <> immediate_prev_room
        ),
        x as (
            select
                shift_id, staff_id, event_index,
                current_room, current_class, current_itype,
                lag(current_room) over(partition by shift_id order by event_index) as prev_room,
                lead(current_room) over(partition by shift_id order by event_index) as action,
                time_bucket, role, roster_unit
            from runs
        )
        select * from x where action is not null
    """)

    metrics: dict[str, float] = {
        "valid_roster_shifts": int(
            con.execute("select count(*) from roster_intervals").fetchone()[0]
        ),
        "staff": int(con.execute("select count(*) from staff_map").fetchone()[0]),
        "roster_overlap_intervals": overlap_count,
        "events_matching_multiple_shifts": multi_candidate_events,
        "canonical_events": int(
            con.execute("select count(*) from canonical_events_internal").fetchone()[0]
        ),
        "shifts_with_activity": int(
            con.execute(
                "select count(distinct shift_id) from canonical_events_internal"
            ).fetchone()[0]
        ),
        "resolved_events": int(
            con.execute(
                "select count(*) from canonical_events_internal where location_resolved"
            ).fetchone()[0]
        ),
        "room_resolved_events": int(
            con.execute(
                "select count(*) from canonical_events_internal where room_resolved"
            ).fetchone()[0]
        ),
        "doorpoint_resolved_events": int(
            con.execute(
                "select count(*) from canonical_events_internal where doorpoint_resolved"
            ).fetchone()[0]
        ),
        "class_pairs": int(
            con.execute("select count(*) from class_pairs").fetchone()[0]
        ),
        "room_observation_pairs": int(
            con.execute("select count(*) from room_observation_pairs").fetchone()[0]
        ),
        "room_change_pairs": int(
            con.execute("select count(*) from room_change_pairs").fetchone()[0]
        ),
    }
    if metrics["canonical_events"]:
        metrics["resolved_event_fraction"] = (
            metrics["resolved_events"] / metrics["canonical_events"]
        )
        metrics["room_resolved_event_fraction"] = (
            metrics["room_resolved_events"] / metrics["canonical_events"]
        )
    else:
        metrics["resolved_event_fraction"] = 0.0
        metrics["room_resolved_event_fraction"] = 0.0
    return metrics


def export_canonical_outputs(
    con: duckdb.DuckDBPyConnection,
    outdir: Path,
    include_timestamps: bool,
    sample_rows: int,
) -> None:
    print("[export] canonical event sequence ...")
    timestamp_col = "event_time," if include_timestamps else ""
    export_query = f"""
        select
            shift_id, staff_id, event_index,
            {timestamp_col}
            minutes_from_shift_start,
            hour_of_day, time_bucket, weekday,
            shift_duration_hours, roster_unit, role,
            interaction_class, interaction_type, source_key, has_patient,
            resolved_location, mapping_type,
            location_resolved, room_resolved, doorpoint_resolved
        from canonical_events_internal
        order by shift_id, event_index
    """
    con.execute(
        f"COPY ({export_query}) TO '{sql_quote(outdir / 'canonical_events.parquet')}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    con.execute(
        f"COPY (select * from ({export_query}) limit {int(sample_rows)}) "
        f"TO '{sql_quote(outdir / 'canonical_events_sample.csv')}' (HEADER, DELIMITER ',')"
    )

    con.execute(f"""
        COPY (
            with base as (
                select
                    r.shift_id,
                    r.staff_id,
                    r.shift_duration_hours,
                    r.roster_unit,
                    min(coalesce(e.role, 'unknown')) as role,
                    count(e.event_index) as total_events,
                    count(*) filter(where e.interaction_class = 'Flowsheet') as flowsheet_events,
                    count(*) filter(where e.interaction_class = 'Workstation') as workstation_events,
                    count(*) filter(where e.interaction_class = 'Door Message') as door_events,
                    count(*) filter(where e.location_resolved) as resolved_events,
                    count(*) filter(where e.room_resolved) as room_resolved_events,
                    count(distinct e.resolved_location) filter(where e.room_resolved) as distinct_rooms,
                    count(distinct e.resolved_location) filter(where e.doorpoint_resolved) as distinct_doorpoints
                from roster_intervals r
                left join canonical_events_internal e using(shift_id, staff_id)
                group by r.shift_id, r.staff_id, r.shift_duration_hours, r.roster_unit
            ), changes as (
                select shift_id, count(*) as observed_room_changes
                from room_change_pairs
                group by shift_id
            )
            select
                b.*,
                b.total_events / nullif(b.shift_duration_hours, 0) as events_per_hour,
                b.resolved_events / nullif(b.total_events::double, 0) as resolved_event_coverage,
                b.room_resolved_events / nullif(b.total_events::double, 0) as room_event_coverage,
                coalesce(c.observed_room_changes, 0) as observed_room_changes,
                coalesce(c.observed_room_changes, 0) / nullif(b.shift_duration_hours, 0) as observed_room_changes_per_hour
            from base b
            left join changes c using(shift_id)
            where b.total_events > 0
            order by b.shift_id
        ) TO '{sql_quote(outdir / "canonical_shift_summary.csv")}' (HEADER, DELIMITER ',')
    """)


def make_shift_split(
    con: duckdb.DuckDBPyConnection, train_fraction: float, seed: int
) -> tuple[int, int]:
    shift_ids = [
        int(r[0])
        for r in con.execute(
            "select distinct shift_id from canonical_events_internal order by shift_id"
        ).fetchall()
    ]
    rng = random.Random(seed)
    rng.shuffle(shift_ids)
    cut = (
        max(1, min(len(shift_ids) - 1, int(len(shift_ids) * train_fraction)))
        if len(shift_ids) >= 2
        else len(shift_ids)
    )
    train = set(shift_ids[:cut])
    rows = [(sid, "train" if sid in train else "test") for sid in shift_ids]
    con.execute(
        "create or replace temp table shift_split (shift_id bigint, split varchar)"
    )
    if rows:
        con.executemany("insert into shift_split values (?, ?)", rows)
    return len(train), len(shift_ids) - len(train)


def write_rows_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def where_clause(group_col: str | None, group_value: str | None) -> tuple[str, list]:
    if group_col is None:
        return "", []
    return f" and cast(p.{group_col} as varchar) = ?", [str(group_value)]


def prepare_eval_tables(
    con: duckdb.DuckDBPyConnection,
    pair_table: str,
    group_col: str | None = None,
    group_value: str | None = None,
) -> tuple[int, int, int, int]:
    extra, params = where_clause(group_col, group_value)
    con.execute("drop table if exists _train_eval")
    con.execute("drop table if exists _test_eval")
    con.execute(
        f"""
        create temp table _train_eval as
        select row_number() over() as eval_id, p.*
        from {pair_table} p
        join shift_split s using(shift_id)
        where s.split = 'train' {extra}
    """,
        params,
    )
    con.execute(
        f"""
        create temp table _test_eval as
        select row_number() over() as eval_id, p.*
        from {pair_table} p
        join shift_split s using(shift_id)
        where s.split = 'test' {extra}
    """,
        params,
    )
    ntr = int(con.execute("select count(*) from _train_eval").fetchone()[0])
    nte = int(con.execute("select count(*) from _test_eval").fetchone()[0])
    strn = int(
        con.execute("select count(distinct shift_id) from _train_eval").fetchone()[0]
    )
    ste = int(
        con.execute("select count(distinct shift_id) from _test_eval").fetchone()[0]
    )
    return ntr, nte, strn, ste


def get_marginal_top(con: duckdb.DuckDBPyConnection) -> tuple[str | None, list[str]]:
    rows = con.execute("""
        select cast(action as varchar), count(*) as n
        from _train_eval
        group by action
        order by n desc, cast(action as varchar)
        limit 3
    """).fetchall()
    if not rows:
        return None, []
    vals = [str(r[0]) for r in rows]
    return vals[0], vals


def evaluate_majority(con: duckdb.DuckDBPyConnection) -> dict:
    top1, top3 = get_marginal_top(con)
    n_test = int(con.execute("select count(*) from _test_eval").fetchone()[0])
    if not top1 or n_test == 0:
        return {"top1": math.nan, "top3": math.nan, "unseen_state_fraction": math.nan}
    padded = (top3 + [None, None, None])[:3]
    row = con.execute(
        """
        select
            avg(case when cast(action as varchar) = ? then 1.0 else 0.0 end),
            avg(case when cast(action as varchar) in (?, ?, ?) then 1.0 else 0.0 end)
        from _test_eval
    """,
        [top1, *padded],
    ).fetchone()
    return {"top1": float(row[0]), "top3": float(row[1]), "unseen_state_fraction": 0.0}


def evaluate_state_model(con: duckdb.DuckDBPyConnection, state_cols: list[str]) -> dict:
    top1, top3 = get_marginal_top(con)
    n_test = int(con.execute("select count(*) from _test_eval").fetchone()[0])
    if not top1 or n_test == 0:
        return {"top1": math.nan, "top3": math.nan, "unseen_state_fraction": math.nan}

    state_select = ", ".join(state_cols)
    partition = ", ".join(state_cols)
    con.execute("drop table if exists _ranked_actions")
    con.execute(f"""
        create temp table _ranked_actions as
        with counts as (
            select {state_select}, cast(action as varchar) as predicted_action, count(*) as n
            from _train_eval
            group by {state_select}, action
        ), ranked as (
            select *,
                   row_number() over(
                       partition by {partition}
                       order by n desc, predicted_action
                   ) as rn
            from counts
        )
        select * from ranked where rn <= 3
    """)

    join_parts = [f"r.{c} is not distinct from t.{c}" for c in state_cols]
    join_sql = " and ".join(join_parts)
    padded = (top3 + [None, None, None])[:3]
    row = con.execute(
        f"""
        with per_pair as (
            select
                t.eval_id,
                cast(t.action as varchar) as actual_action,
                max(case when r.rn is not null then 1 else 0 end) as state_seen,
                max(case when r.rn = 1 and r.predicted_action = cast(t.action as varchar) then 1 else 0 end) as seen_hit1,
                max(case when r.rn <= 3 and r.predicted_action = cast(t.action as varchar) then 1 else 0 end) as seen_hit3
            from _test_eval t
            left join _ranked_actions r
              on {join_sql}
            group by t.eval_id, t.action
        )
        select
            avg(case
                  when state_seen = 1 then seen_hit1::double
                  when actual_action = ? then 1.0 else 0.0 end) as top1,
            avg(case
                  when state_seen = 1 then seen_hit3::double
                  when actual_action in (?, ?, ?) then 1.0 else 0.0 end) as top3,
            avg(case when state_seen = 0 then 1.0 else 0.0 end) as unseen_frac
        from per_pair
    """,
        [top1, *padded],
    ).fetchone()
    return {
        "top1": float(row[0]),
        "top3": float(row[1]),
        "unseen_state_fraction": float(row[2]),
    }


def task_models(task: str) -> list[tuple[str, list[str] | None]]:
    if task == "next_class":
        return [
            ("majority", None),
            ("markov_current_class", ["current_class"]),
            ("current_plus_previous_class", ["current_class", "prev_class"]),
            ("plus_time_role", ["current_class", "prev_class", "time_bucket", "role"]),
            (
                "full_context",
                ["current_class", "prev_class", "time_bucket", "role", "roster_unit"],
            ),
        ]
    return [
        ("majority", None),
        ("markov_current_room", ["current_room"]),
        ("current_plus_previous_room", ["current_room", "prev_room"]),
        ("plus_time", ["current_room", "prev_room", "time_bucket"]),
        ("plus_role", ["current_room", "prev_room", "time_bucket", "role"]),
        (
            "full_context",
            [
                "current_room",
                "prev_room",
                "time_bucket",
                "role",
                "current_class",
                "roster_unit",
            ],
        ),
    ]


def run_pooled_learnability(con: duckdb.DuckDBPyConnection) -> list[dict]:
    task_tables = {
        "next_class": "class_pairs",
        "next_room_observation": "room_observation_pairs",
        "next_room_change": "room_change_pairs",
    }
    out: list[dict] = []
    for task, table in task_tables.items():
        ntr, nte, strn, ste = prepare_eval_tables(con, table)
        print(f"[learnability] {task}: {ntr} train pairs / {nte} test pairs")
        for model_name, cols in task_models(task):
            score = (
                evaluate_majority(con)
                if cols is None
                else evaluate_state_model(con, cols)
            )
            out.append(
                {
                    "task": task,
                    "population": "pooled",
                    "model": model_name,
                    "train_pairs": ntr,
                    "test_pairs": nte,
                    "train_shifts": strn,
                    "test_shifts": ste,
                    **score,
                }
            )
    return out


def entropy_from_counts(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return math.nan
    h = 0.0
    for n in counts:
        if n <= 0:
            continue
        p = n / total
        h -= p * math.log2(p)
    return h


def entropy_summary(con: duckdb.DuckDBPyConnection) -> list[dict]:
    specs = [
        ("next_class", "class_pairs", "current_class"),
        ("next_room_observation", "room_observation_pairs", "current_room"),
        ("next_room_change", "room_change_pairs", "current_room"),
    ]
    rows: list[dict] = []
    for task, table, state_col in specs:
        action_counts = [
            int(x[0])
            for x in con.execute(
                f"select count(*) from {table} group by action"
            ).fetchall()
        ]
        h_action = entropy_from_counts(action_counts)

        state_rows = con.execute(f"""
            select cast({state_col} as varchar), cast(action as varchar), count(*)
            from {table}
            group by {state_col}, action
        """).fetchall()
        by_state: dict[str, list[int]] = {}
        for state, _action, n in state_rows:
            by_state.setdefault(str(state), []).append(int(n))
        total = sum(sum(v) for v in by_state.values())
        h_cond = 0.0
        if total:
            for vals in by_state.values():
                n = sum(vals)
                h_cond += (n / total) * entropy_from_counts(vals)
        else:
            h_cond = math.nan
        rows.append(
            {
                "task": task,
                "conditioning_state": state_col,
                "H_action_bits": h_action,
                "H_action_given_state_bits": h_cond,
                "information_gain_bits": h_action - h_cond
                if math.isfinite(h_action) and math.isfinite(h_cond)
                else math.nan,
            }
        )
    return rows


def eligible_groups(
    con: duckdb.DuckDBPyConnection,
    pair_table: str,
    group_col: str,
    min_shifts: int,
    min_test_pairs: int,
) -> list[tuple[str, int, int]]:
    rows = con.execute(
        f"""
        select
            cast(p.{group_col} as varchar) as group_value,
            count(distinct p.shift_id) as n_shifts,
            count(*) filter(where s.split = 'test') as test_pairs
        from {pair_table} p
        join shift_split s using(shift_id)
        group by p.{group_col}
        having count(distinct p.shift_id) >= ?
           and count(*) filter(where s.split = 'test') >= ?
        order by n_shifts desc, group_value
    """,
        [int(min_shifts), int(min_test_pairs)],
    ).fetchall()
    return [(str(v), int(n), int(t)) for v, n, t in rows]


def run_subgroup_learnability(
    con: duckdb.DuckDBPyConnection, min_shifts: int, min_test_pairs: int
) -> list[dict]:
    # Subgroups for the spatial tasks only.
    task_tables = {
        "next_room_observation": "room_observation_pairs",
        "next_room_change": "room_change_pairs",
    }
    out: list[dict] = []
    for task, table in task_tables.items():
        for group_col in ("role", "roster_unit"):
            groups = eligible_groups(con, table, group_col, min_shifts, min_test_pairs)
            print(f"[subgroups] {task} x {group_col}: {len(groups)} eligible groups")
            for value, group_shifts, _ in groups:
                ntr, nte, strn, ste = prepare_eval_tables(con, table, group_col, value)
                for model_name, cols in [
                    ("majority", None),
                    ("markov_current_room", ["current_room"]),
                    (
                        "full_context",
                        [
                            "current_room",
                            "prev_room",
                            "time_bucket",
                            "role",
                            "current_class",
                            "roster_unit",
                        ],
                    ),
                ]:
                    score = (
                        evaluate_majority(con)
                        if cols is None
                        else evaluate_state_model(con, cols)
                    )
                    out.append(
                        {
                            "task": task,
                            "group_type": group_col,
                            "group_value": value,
                            "group_shifts_total": group_shifts,
                            "model": model_name,
                            "train_pairs": ntr,
                            "test_pairs": nte,
                            "train_shifts": strn,
                            "test_shifts": ste,
                            **score,
                        }
                    )
    return out


def quality_rows(metrics: dict, location_records: list[tuple]) -> list[dict]:
    rows = [{"metric": k, "value": v} for k, v in metrics.items()]
    ctr = Counter((r[0], r[3]) for r in location_records)
    for (iclass, mtype), n in sorted(ctr.items()):
        rows.append({"metric": f"location_map__{iclass}__{mtype}", "value": n})
    return rows


def best_model(rows: list[dict], task: str) -> dict | None:
    candidates = [
        r
        for r in rows
        if r.get("task") == task
        and r.get("population") == "pooled"
        and isinstance(r.get("top1"), (int, float))
        and math.isfinite(float(r["top1"]))
    ]
    return max(candidates, key=lambda r: float(r["top1"])) if candidates else None


def model_row(rows: list[dict], task: str, model: str) -> dict | None:
    for r in rows:
        if (
            r.get("task") == task
            and r.get("model") == model
            and r.get("population") == "pooled"
        ):
            return r
    return None


def fmt_pct(x) -> str:
    try:
        x = float(x)
        return f"{100 * x:.1f}%" if math.isfinite(x) else "NA"
    except Exception:
        return "NA"


def fmt_num(x, digits=3) -> str:
    try:
        x = float(x)
        return f"{x:.{digits}f}" if math.isfinite(x) else "NA"
    except Exception:
        return "NA"


def svg_bar_chart(rows: list[dict], task: str, path: Path, title: str) -> None:
    data = [
        r for r in rows if r.get("task") == task and r.get("population") == "pooled"
    ]
    if not data:
        return
    width, height = 900, 480
    left, right, top, bottom = 110, 30, 70, 135
    chart_w = width - left - right
    chart_h = height - top - bottom
    n = len(data)
    gap = 20
    bar_w = max(35, (chart_w - gap * (n + 1)) / max(1, n))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="32" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="bold">{html.escape(title)}</text>',
    ]
    # grid / y labels
    for j in range(0, 11, 2):
        val = j / 10
        y = top + chart_h * (1 - val)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#dddddd"/>'
        )
        parts.append(
            f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" font-family="sans-serif" font-size="12">{int(val * 100)}%</text>'
        )
    for i, r in enumerate(data):
        v = (
            max(0.0, min(1.0, float(r["top1"])))
            if math.isfinite(float(r["top1"]))
            else 0.0
        )
        x = left + gap + i * (bar_w + gap)
        h = v * chart_h
        y = top + chart_h - h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="#6b7280"/>'
        )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 7:.1f}" text-anchor="middle" font-family="sans-serif" font-size="12">{100 * v:.1f}%</text>'
        )
        label = str(r["model"]).replace("_", " ")
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{top + chart_h + 18:.1f}" text-anchor="end" transform="rotate(-35 {x + bar_w / 2:.1f} {top + chart_h + 18:.1f})" font-family="sans-serif" font-size="12">{html.escape(label)}</text>'
        )
    parts.append(
        f'<text x="20" y="{top + chart_h / 2}" text-anchor="middle" transform="rotate(-90 20 {top + chart_h / 2})" font-family="sans-serif" font-size="14">Held-out top-1 accuracy</text>'
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_subgroup_chart(
    rows: list[dict],
    task: str,
    group_type: str,
    path: Path,
    title: str,
    max_groups: int = 12,
) -> None:
    groups: dict[str, dict[str, dict]] = {}
    for r in rows:
        if r.get("task") == task and r.get("group_type") == group_type:
            groups.setdefault(str(r["group_value"]), {})[str(r["model"])] = r
    items = []
    for g, models in groups.items():
        if "markov_current_room" in models and "full_context" in models:
            items.append((g, models["markov_current_room"], models["full_context"]))
    items.sort(key=lambda x: int(x[2].get("test_pairs", 0)), reverse=True)
    items = items[:max_groups]
    if not items:
        return

    width = max(900, 120 + 90 * len(items))
    height = 500
    left, right, top, bottom = 90, 30, 75, 145
    chart_w, chart_h = width - left - right, height - top - bottom
    group_w = chart_w / len(items)
    bar_w = min(28, group_w * 0.28)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="32" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="bold">{html.escape(title)}</text>',
        '<text x="90" y="55" font-family="sans-serif" font-size="12">dark = current-room Markov; light = full context</text>',
    ]
    for j in range(0, 11, 2):
        v = j / 10
        y = top + chart_h * (1 - v)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#dddddd"/>'
        )
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="sans-serif" font-size="12">{int(v * 100)}%</text>'
        )
    for i, (g, mk, full) in enumerate(items):
        cx = left + group_w * (i + 0.5)
        for dx, r, fill in [
            (-bar_w * 0.6, mk, "#4b5563"),
            (bar_w * 0.6, full, "#9ca3af"),
        ]:
            v = max(0, min(1, float(r["top1"])))
            h = v * chart_h
            x = cx + dx - bar_w / 2
            y = top + chart_h - h
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{fill}"/>'
            )
        parts.append(
            f'<text x="{cx:.1f}" y="{top + chart_h + 18}" text-anchor="end" transform="rotate(-40 {cx:.1f} {top + chart_h + 18})" font-family="sans-serif" font-size="11">{html.escape(g[:35])}</text>'
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_report(
    outdir: Path,
    metrics: dict,
    pooled: list[dict],
    entropy: list[dict],
    subgroups: list[dict],
    train_shifts: int,
    test_shifts: int,
    crosswalk: Path | None,
) -> None:
    def pooled_table(task: str) -> str:
        rs = [r for r in pooled if r["task"] == task]
        lines = ["| Model | Top-1 | Top-3 | Unseen states |", "|---|---:|---:|---:|"]
        for r in rs:
            lines.append(
                f"| {r['model']} | {fmt_pct(r['top1'])} | {fmt_pct(r['top3'])} | {fmt_pct(r['unseen_state_fraction'])} |"
            )
        return "\n".join(lines)

    def entropy_line(task: str) -> str:
        r = next((x for x in entropy if x["task"] == task), None)
        if not r:
            return "NA"
        return (
            f"H(action)={fmt_num(r['H_action_bits'], 2)} bits; "
            f"H(action|current state)={fmt_num(r['H_action_given_state_bits'], 2)} bits; "
            f"information gain={fmt_num(r['information_gain_bits'], 2)} bits."
        )

    room_change_markov = model_row(pooled, "next_room_change", "markov_current_room")
    room_change_full = model_row(pooled, "next_room_change", "full_context")
    lift_text = "NA"
    if room_change_markov and room_change_full:
        lift = float(room_change_full["top1"]) - float(room_change_markov["top1"])
        lift_text = f"{lift:+.3f} ({lift * 100:+.1f} percentage points)"

    text = f"""# AMR-HUB learnability report

Held-out prediction on whole shifts (no clustering).

## Data

- Canonical events: {metrics.get("canonical_events", 0):,}
- Shifts with activity: {metrics.get("shifts_with_activity", 0):,}
- Staff: {metrics.get("staff", 0):,}
- Spatially resolved events: {fmt_pct(metrics.get("resolved_event_fraction", 0))}
- Room-resolved events: {fmt_pct(metrics.get("room_resolved_event_fraction", 0))}
- Overlapping roster intervals: {metrics.get("roster_overlap_intervals", 0):,}
- Events matching more than one interval: {metrics.get("events_matching_multiple_shifts", 0):,}
- Workstation crosswalk: `{crosswalk if crosswalk else "none"}`
- Train/test shifts: {train_shifts:,} / {test_shifts:,}

## Next event class

{pooled_table("next_class")}

Entropy: {entropy_line("next_class")}

## Next room observation

Consecutive room-resolved observations, including repeats of the same room.

{pooled_table("next_room_observation")}

Entropy: {entropy_line("next_room_observation")}

## Next room change

Consecutive repeats of the same room collapsed first.

{pooled_table("next_room_change")}

Entropy: {entropy_line("next_room_change")}

Full context vs current-room Markov: {lift_text}

## Subgroups

`subgroup_learnability.csv`: majority, current-room Markov and full context within role and
roster-unit groups, same split. Figures 04 and 05 show next room change.

## Notes

- Door points are kept in `canonical_events.parquet` but are not rooms in the room tasks.
- A room change is a change between recorded observations, not the physical path.
- Workstations are placed only where the crosswalk has a room.
"""
    (outdir / "LEARNABILITY_REPORT.md").write_text(text, encoding="utf-8")


def write_index(outdir: Path) -> None:
    text = """AMR-HUB canonical sequence and learnability

Report:
  LEARNABILITY_REPORT.md

Data:
  canonical_events.parquet
  canonical_events_sample.csv
  canonical_shift_summary.csv
  spatial_location_map_used.csv

Results:
  quality_summary.csv
  entropy_summary.csv
  pooled_learnability.csv
  subgroup_learnability.csv

Figures:
  01_next_class_learnability.svg
  02_next_room_observation_learnability.svg
  03_next_room_change_learnability.svg
  04_role_room_change_learnability.svg
  05_unit_room_change_learnability.svg
"""
    (outdir / "REPORT_INDEX.txt").write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="AMR-HUB canonical sequence and learnability analysis"
    )
    ap.add_argument(
        "--db", default=None, help="DuckDB filename in /data, or absolute path"
    )
    ap.add_argument(
        "--out", default="/outputs/learnability_analysis", help="New output directory"
    )
    ap.add_argument(
        "--crosswalk",
        default=None,
        help="Workstation crosswalk; defaults to /outputs/ws_crosswalk.csv",
    )
    ap.add_argument("--train-fraction", type=float, default=DEFAULT_TRAIN_FRACTION)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--min-group-shifts", type=int, default=DEFAULT_MIN_GROUP_SHIFTS)
    ap.add_argument(
        "--min-group-test-pairs", type=int, default=DEFAULT_MIN_GROUP_TEST_PAIRS
    )
    ap.add_argument(
        "--sample-rows",
        type=int,
        default=5000,
        help="Rows in canonical_events_sample.csv",
    )
    ap.add_argument(
        "--include-timestamps",
        action="store_true",
        help="Include absolute event_time in exported canonical table",
    )
    args = ap.parse_args()

    if not (0.5 <= args.train_fraction < 1.0):
        raise SystemExit("--train-fraction must be >=0.5 and <1.0")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    db_path = find_database(args.db)
    crosswalk_path = (
        Path(args.crosswalk) if args.crosswalk else Path("/outputs/ws_crosswalk.csv")
    )
    crosswalk = crosswalk_path if crosswalk_path.exists() else None

    print(f"[db] {db_path}")
    print(f"[out] {outdir}")
    print(f"[crosswalk] {crosswalk if crosswalk else 'none'}")

    con = connect_database(db_path)
    try:
        location_records = create_location_map(con, crosswalk)
        with (outdir / "spatial_location_map_used.csv").open(
            "w", newline="", encoding="utf-8"
        ) as f:
            w = csv.writer(f)
            w.writerow(["iclass", "source_key", "resolved_location", "mapping_type"])
            map_rows = sorted(location_records, key=lambda x: (x[0], x[1]))
            w.writerows(map_rows)

        metrics = create_canonical_tables(con)
        export_canonical_outputs(con, outdir, args.include_timestamps, args.sample_rows)

        train_shifts, test_shifts = make_shift_split(
            con, args.train_fraction, args.seed
        )
        pooled = run_pooled_learnability(con)
        entropy = entropy_summary(con)
        subgroups = run_subgroup_learnability(
            con, args.min_group_shifts, args.min_group_test_pairs
        )

        write_rows_csv(
            outdir / "quality_summary.csv", quality_rows(metrics, location_records)
        )
        write_rows_csv(outdir / "pooled_learnability.csv", pooled)
        write_rows_csv(outdir / "entropy_summary.csv", entropy)
        write_rows_csv(outdir / "subgroup_learnability.csv", subgroups)

        svg_bar_chart(
            pooled,
            "next_class",
            outdir / "01_next_class_learnability.svg",
            "Held-out learnability: next event class",
        )
        svg_bar_chart(
            pooled,
            "next_room_observation",
            outdir / "02_next_room_observation_learnability.svg",
            "Held-out learnability: next observed room",
        )
        svg_bar_chart(
            pooled,
            "next_room_change",
            outdir / "03_next_room_change_learnability.svg",
            "Held-out learnability: next observed room change",
        )
        svg_subgroup_chart(
            subgroups,
            "next_room_change",
            "role",
            outdir / "04_role_room_change_learnability.svg",
            "Next-room-change learnability by role",
        )
        svg_subgroup_chart(
            subgroups,
            "next_room_change",
            "roster_unit",
            outdir / "05_unit_room_change_learnability.svg",
            "Next-room-change learnability by roster unit",
        )

        write_report(
            outdir,
            metrics,
            pooled,
            entropy,
            subgroups,
            train_shifts,
            test_shifts,
            crosswalk,
        )
        write_index(outdir)

        print("\n=== COMPLETE ===")
        print(f"Canonical events: {metrics['canonical_events']:,}")
        print(f"Train/test shifts: {train_shifts:,} / {test_shifts:,}")
        for task in ("next_class", "next_room_observation", "next_room_change"):
            b = best_model(pooled, task)
            if b:
                print(f"{task}: best pooled top1 = {b['top1']:.3f} ({b['model']})")
        print(f"\nOpen: {outdir / 'LEARNABILITY_REPORT.md'}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
