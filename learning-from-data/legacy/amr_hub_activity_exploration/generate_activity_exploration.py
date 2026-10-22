#!/usr/bin/env python3
"""Descriptive activity and transition summaries for rostered shifts.

The database is attached as catalog `output` because stored views refer to it.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DOOR_CODE_RE = re.compile(r"\b(?:E\d{2})?[A-Z]{2}\d{2,3}[A-Z]?\b", re.IGNORECASE)
DEFAULT_TOP_LOCATIONS = 20


def std_code(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).upper()


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
    sql_path = str(db_path).replace("'", "''")
    con.execute(f"ATTACH '{sql_path}' AS output (READ_ONLY)")
    con.execute("USE output")
    return con


def load_crosswalk(path: Path | None) -> dict[int, str]:
    if path is None or not path.exists():
        return {}
    df = pd.read_csv(path)
    required = {"source_key", "room"}
    if not required.issubset(df.columns):
        print(f"[crosswalk] {path} lacks required columns {sorted(required)}; ignored.")
        return {}
    if "iclass" in df.columns:
        df = df[df["iclass"].astype(str).str.strip().eq("Workstation")]
    df = df[df["room"].notna() & df["room"].astype(str).str.strip().ne("")]
    out = {
        int(row.source_key): f"room:{std_code(row.room)}"
        for row in df.itertuples(index=False)
    }
    print(f"[crosswalk] {len(out)} workstation room mappings loaded from {path}")
    return out


def build_location_map(
    con: duckdb.DuckDBPyConnection, crosswalk: Path | None
) -> pd.DataFrame:
    records: list[dict] = []

    try:
        dep = con.execute("""
            select DepartmentKey, RoomName
            from Ref.Department
            where DepartmentKey is not null and RoomName is not null
        """).df()
        for row in dep.itertuples(index=False):
            records.append(
                {
                    "iclass": "Flowsheet",
                    "source_key": int(row.DepartmentKey),
                    "resolved_location": f"room:{std_code(row.RoomName)}",
                    "mapping_type": "room",
                }
            )
        print(f"[locations] {len(dep)} flowsheet/department rows available")
    except duckdb.Error as exc:
        print(f"[locations] WARNING: could not read Ref.Department: {exc}")

    ws_map = load_crosswalk(crosswalk)
    for key, loc in ws_map.items():
        records.append(
            {
                "iclass": "Workstation",
                "source_key": key,
                "resolved_location": loc,
                "mapping_type": "room",
            }
        )

    try:
        doors = con.execute("""
            select DoorKey, DoorName
            from Ref.Door
            where DoorKey is not null and DoorName is not null
        """).df()
        n_door = 0
        for row in doors.itertuples(index=False):
            match = DOOR_CODE_RE.search(std_code(row.DoorName))
            if match is None:
                continue
            code = match.group(0).upper()
            records.append(
                {
                    "iclass": "Door Message",
                    "source_key": int(row.DoorKey),
                    "resolved_location": f"doorpoint:{code}#DOORKEY:{int(row.DoorKey)}",
                    "mapping_type": "doorpoint",
                }
            )
            n_door += 1
        print(f"[locations] {n_door}/{len(doors)} doors received a door-point code")
    except duckdb.Error as exc:
        print(f"[locations] WARNING: could not read Ref.Door: {exc}")

    if not records:
        return pd.DataFrame(
            columns=["iclass", "source_key", "resolved_location", "mapping_type"]
        )

    df = pd.DataFrame(records).drop_duplicates(["iclass", "source_key"], keep="last")
    return df


def create_analysis_tables(
    con: duckdb.DuckDBPyConnection, locmap: pd.DataFrame
) -> None:
    print("[sql] building valid roster intervals ...")
    con.execute("""
        create or replace temp table roster_intervals_raw as
        with paired as (
            select
                cast(e.MasterIndexId as varchar) as staff,
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
            p.staff,
            p.link_key,
            p.shift_start,
            p.shift_end,
            p.roster_key,
            coalesce(r.RosterName, 'unknown') as roster_unit,
            (epoch(p.shift_end) - epoch(p.shift_start)) / 3600.0 as shift_duration_hours
        from paired p
        left join Ref.Roster r
          on p.roster_key = r.RosterKey
        where p.shift_start is not null
          and p.shift_end is not null
          and p.shift_end > p.shift_start
    """)

    # Sequential shift IDs; raw staff/link IDs stay inside DuckDB.
    con.execute("""
        create or replace temp table roster_intervals as
        select
            row_number() over(order by staff, shift_start, link_key) as shift_id,
            *
        from roster_intervals_raw
    """)

    overlap_count = con.execute("""
        with x as (
            select
                staff,
                shift_start,
                shift_end,
                lag(shift_end) over(partition by staff order by shift_start, shift_end) as prev_end
            from roster_intervals
        )
        select count(*)
        from x
        where prev_end is not null and shift_start <= prev_end
    """).fetchone()[0]
    print(f"[quality] overlapping roster intervals detected: {overlap_count}")

    print("[sql] assigning activity events to roster intervals ...")
    # Range join: an event inside overlapping intervals is counted in each (see overlap_count).
    con.execute("""
        create or replace temp table activity_in_shift as
        select
            ri.shift_id,
            ri.staff,
            ri.link_key,
            ri.shift_start,
            ri.shift_end,
            ri.shift_duration_hours,
            ri.roster_unit,
            e.EventDateTime as event_time,
            epoch(e.EventDateTime) as ts,
            e.SourceKey as source_key,
            it.InteractionType as itype,
            it.InteractionTypeClass as iclass,
            coalesce(s.Role, 'unknown') as role
        from roster_intervals ri
        join Data.StaffLocationEvent e
          on cast(e.MasterIndexId as varchar) = ri.staff
         and e.EventDateTime between ri.shift_start and ri.shift_end
        join Ref.InteractionType it
          on e.InteractionTypeKey = it.InteractionTypeKey
        left join Ref.Staff s
          on s.MasterIndexId = e.MasterIndexId
        where it.InteractionTypeClass <> 'Roster'
    """)

    if locmap.empty:
        con.execute("""
            create or replace temp table location_map (
                iclass varchar,
                source_key bigint,
                resolved_location varchar,
                mapping_type varchar
            )
        """)
    else:
        con.register("_locmap_df", locmap)
        con.execute("""
            create or replace temp table location_map as
            select
                cast(iclass as varchar) as iclass,
                cast(source_key as bigint) as source_key,
                cast(resolved_location as varchar) as resolved_location,
                cast(mapping_type as varchar) as mapping_type
            from _locmap_df
        """)
        con.unregister("_locmap_df")

    con.execute("""
        create or replace temp table activity_mapped as
        select
            a.*,
            lm.resolved_location,
            lm.mapping_type
        from activity_in_shift a
        left join location_map lm
          on lm.iclass = a.iclass
         and lm.source_key = cast(a.source_key as bigint)
    """)

    # Resolved locations only; unresolved events are skipped.
    con.execute("""
        create or replace temp table resolved_ordered as
        select
            *,
            lag(resolved_location) over(
                partition by shift_id order by event_time, ts, iclass, source_key
            ) as prev_resolved_location
        from activity_mapped
        where resolved_location is not null
    """)

    con.execute("""
        create or replace temp table class_ordered as
        select
            *,
            lag(iclass) over(
                partition by shift_id order by event_time, ts, iclass, source_key
            ) as prev_class
        from activity_mapped
    """)


def export_shift_features(con: duckdb.DuckDBPyConnection, outdir: Path) -> pd.DataFrame:
    print("[analysis] calculating shift-level activity features ...")
    df = con.execute("""
        with basic as (
            select
                ri.shift_id,
                ri.shift_duration_hours,
                ri.roster_unit,
                min(coalesce(a.role, 'unknown')) as role,
                count(a.iclass) as total_events,
                count(*) filter(where a.iclass = 'Flowsheet') as flowsheet_events,
                count(*) filter(where a.iclass = 'Workstation') as workstation_events,
                count(*) filter(where a.iclass = 'Door Message') as door_events,
                count(distinct a.source_key) filter(where a.iclass = 'Workstation') as distinct_workstations,
                count(a.resolved_location) as resolved_events,
                count(distinct a.resolved_location) filter(where a.resolved_location is not null) as distinct_resolved_locations,
                count(distinct a.resolved_location) filter(where a.resolved_location like 'room:%') as distinct_rooms,
                count(distinct a.resolved_location) filter(where a.resolved_location like 'doorpoint:%') as distinct_doorpoints
            from roster_intervals ri
            left join activity_mapped a using(shift_id)
            group by ri.shift_id, ri.shift_duration_hours, ri.roster_unit
        ),
        loc_trans as (
            select
                shift_id,
                count(*) filter(where prev_resolved_location is not null) as resolved_transitions,
                count(*) filter(
                    where prev_resolved_location is not null
                      and resolved_location <> prev_resolved_location
                ) as location_changes,
                count(*) filter(
                    where prev_resolved_location is not null
                      and resolved_location = prev_resolved_location
                ) as same_location_repeats,
                count(distinct prev_resolved_location || ' -> ' || resolved_location)
                    filter(where prev_resolved_location is not null) as distinct_location_transition_types,
                count(distinct prev_resolved_location || ' -> ' || resolved_location)
                    filter(where prev_resolved_location is not null
                             and resolved_location <> prev_resolved_location) as distinct_change_transition_types
            from resolved_ordered
            group by shift_id
        )
        select
            b.*,
            b.total_events / nullif(b.shift_duration_hours, 0) as events_per_hour,
            b.flowsheet_events / nullif(b.total_events::double, 0) as prop_flowsheet,
            b.workstation_events / nullif(b.total_events::double, 0) as prop_workstation,
            b.door_events / nullif(b.total_events::double, 0) as prop_door,
            b.resolved_events / nullif(b.total_events::double, 0) as resolved_event_coverage,
            coalesce(t.resolved_transitions, 0) as resolved_transitions,
            coalesce(t.location_changes, 0) as location_changes,
            coalesce(t.same_location_repeats, 0) as same_location_repeats,
            coalesce(t.distinct_location_transition_types, 0) as distinct_location_transition_types,
            coalesce(t.distinct_change_transition_types, 0) as distinct_change_transition_types,
            coalesce(t.location_changes, 0) / nullif(b.shift_duration_hours, 0) as location_changes_per_hour,
            coalesce(t.same_location_repeats, 0) / nullif(t.resolved_transitions::double, 0) as same_location_repeat_share,
            coalesce(t.distinct_change_transition_types, 0) / nullif(t.location_changes::double, 0) as change_transition_diversity
        from basic b
        left join loc_trans t using(shift_id)
        order by b.shift_id
    """).df()

    df = df[df["total_events"] > 0].copy()
    df.to_csv(outdir / "shift_activity_features.csv", index=False)
    return df


def export_class_transitions(con: duckdb.DuckDBPyConnection, outdir: Path):
    counts = con.execute("""
        select
            prev_class as from_class,
            iclass as to_class,
            count(*) as transition_count
        from class_ordered
        where prev_class is not null
        group by prev_class, iclass
        order by prev_class, transition_count desc, iclass
    """).df()
    counts["from_total"] = counts.groupby("from_class")["transition_count"].transform(
        "sum"
    )
    counts["probability"] = counts["transition_count"] / counts["from_total"]

    counts[["from_class", "to_class", "transition_count"]].to_csv(
        outdir / "class_transition_counts.csv", index=False
    )
    counts[
        ["from_class", "to_class", "transition_count", "from_total", "probability"]
    ].to_csv(outdir / "class_transition_probabilities.csv", index=False)

    matrix = counts.pivot(
        index="from_class", columns="to_class", values="probability"
    ).fillna(0)
    matrix.to_csv(outdir / "class_transition_probability_matrix.csv")

    per_shift = con.execute("""
        select
            shift_id,
            prev_class as from_class,
            iclass as to_class,
            count(*) as transition_count
        from class_ordered
        where prev_class is not null
        group by shift_id, prev_class, iclass
        order by shift_id, prev_class, iclass
    """).df()
    if not per_shift.empty:
        per_shift["from_total"] = per_shift.groupby(["shift_id", "from_class"])[
            "transition_count"
        ].transform("sum")
        per_shift["probability"] = (
            per_shift["transition_count"] / per_shift["from_total"]
        )
        per_shift.to_csv(
            outdir / "per_shift_class_transition_probabilities_long.csv", index=False
        )

        per_shift["feature"] = (
            "p_"
            + per_shift["from_class"].astype(str).str.replace(r"\W+", "_", regex=True)
            + "_to_"
            + per_shift["to_class"].astype(str).str.replace(r"\W+", "_", regex=True)
        )
        wide = per_shift.pivot_table(
            index="shift_id", columns="feature", values="probability", fill_value=0
        ).reset_index()
        wide.columns.name = None
        wide.to_csv(outdir / "per_shift_class_transition_features.csv", index=False)
    else:
        pd.DataFrame(columns=["shift_id"]).to_csv(
            outdir / "per_shift_class_transition_features.csv", index=False
        )

    return counts, matrix


def export_location_transitions(
    con: duckdb.DuckDBPyConnection, outdir: Path, top_n: int
):
    # Changes only: A->A repeats are ignored.
    counts = con.execute("""
        select
            prev_resolved_location as from_location,
            resolved_location as to_location,
            count(*) as transition_count
        from resolved_ordered
        where prev_resolved_location is not null
          and resolved_location <> prev_resolved_location
        group by prev_resolved_location, resolved_location
        order by transition_count desc, from_location, to_location
    """).df()

    if counts.empty:
        counts.to_csv(outdir / "location_transition_counts.csv", index=False)
        counts.to_csv(outdir / "location_transition_probabilities.csv", index=False)
        pd.DataFrame().to_csv(
            outdir / f"location_transition_probability_matrix_top{top_n}.csv"
        )
        return counts, pd.DataFrame()

    counts["from_total"] = counts.groupby("from_location")[
        "transition_count"
    ].transform("sum")
    counts["probability"] = counts["transition_count"] / counts["from_total"]
    counts[["from_location", "to_location", "transition_count"]].to_csv(
        outdir / "location_transition_counts.csv", index=False
    )
    counts.to_csv(outdir / "location_transition_probabilities.csv", index=False)

    participation = (
        pd.concat(
            [
                counts.groupby("from_location")["transition_count"]
                .sum()
                .rename("count"),
                counts.groupby("to_location")["transition_count"].sum().rename("count"),
            ]
        )
        .groupby(level=0)
        .sum()
        .sort_values(ascending=False)
    )
    top_locations = participation.head(top_n).index.tolist()

    top = counts[
        counts["from_location"].isin(top_locations)
        & counts["to_location"].isin(top_locations)
    ].copy()

    # Re-normalised within the displayed top-N; full probabilities are in the CSV.
    if not top.empty:
        top["shown_from_total"] = top.groupby("from_location")[
            "transition_count"
        ].transform("sum")
        top["shown_probability"] = top["transition_count"] / top["shown_from_total"]
        matrix = top.pivot(
            index="from_location", columns="to_location", values="shown_probability"
        ).fillna(0)
        matrix = matrix.reindex(
            index=top_locations, columns=top_locations, fill_value=0
        )
    else:
        matrix = pd.DataFrame(index=top_locations, columns=top_locations).fillna(0)

    matrix.to_csv(outdir / f"location_transition_probability_matrix_top{top_n}.csv")
    pd.DataFrame(
        {
            "location": top_locations,
            "transition_participation_count": participation.reindex(
                top_locations
            ).values,
        }
    ).to_csv(outdir / f"top{top_n}_transition_locations.csv", index=False)
    return counts, matrix


def safe_quantile(series: pd.Series, q: float, default: float = 1.0) -> float:
    x = (
        pd.to_numeric(series, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if x.empty:
        return default
    val = float(x.quantile(q))
    return val if math.isfinite(val) and val > 0 else default


def save_hist(
    series: pd.Series,
    title: str,
    xlabel: str,
    path: Path,
    bins: int = 40,
    qmax: float = 0.99,
):
    x = (
        pd.to_numeric(series, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if x.empty:
        return
    cap = safe_quantile(x, qmax, float(x.max()) if len(x) else 1.0)
    shown = x[x <= cap]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.hist(shown, bins=bins)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Number of rostered shifts")
    ax.grid(axis="y", alpha=0.2)
    ax.text(
        0.99,
        0.98,
        f"Display capped at {qmax:.0%} percentile = {cap:.2f}\nAll values remain in CSV",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_activity_composition(df: pd.DataFrame, path: Path):
    cols = [
        c
        for c in ["prop_flowsheet", "prop_workstation", "prop_door"]
        if c in df.columns
    ]
    if not cols:
        return
    labels = [c.replace("prop_", "").replace("_", " ").title() for c in cols]
    data = [(pd.to_numeric(df[c], errors="coerce") * 100).dropna().values for c in cols]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.boxplot(data, labels=labels, showfliers=False)
    ax.set_title("Activity composition per shift")
    ax.set_ylabel("Percentage of recorded activity events in shift")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.2)
    ax.text(
        0.99,
        0.02,
        "Outliers hidden",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_heatmap(matrix: pd.DataFrame, title: str, path: Path, annotate: bool = True):
    if matrix.empty:
        return
    vals = matrix.to_numpy(dtype=float)
    nrow, ncol = vals.shape
    width = max(7.5, min(16, 0.55 * ncol + 4))
    height = max(6, min(16, 0.5 * nrow + 3))
    fig, ax = plt.subplots(figsize=(width, height))
    im = ax.imshow(vals, aspect="auto", vmin=0, vmax=max(1e-9, float(np.nanmax(vals))))
    fig.colorbar(im, ax=ax, label="Transition probability")
    ax.set_title(title)
    ax.set_xlabel("Next state")
    ax.set_ylabel("Current state")
    ax.set_xticks(range(ncol))
    ax.set_yticks(range(nrow))
    ax.set_xticklabels(
        [str(x) for x in matrix.columns], rotation=60, ha="right", fontsize=8
    )
    ax.set_yticklabels([str(x) for x in matrix.index], fontsize=8)
    if annotate and nrow * ncol <= 100:
        for i in range(nrow):
            for j in range(ncol):
                if vals[i, j] > 0:
                    ax.text(
                        j, i, f"{vals[i, j]:.2f}", ha="center", va="center", fontsize=8
                    )
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_scatter(df: pd.DataFrame, path: Path):
    x = pd.to_numeric(df["events_per_hour"], errors="coerce")
    y = pd.to_numeric(df["location_changes_per_hour"], errors="coerce")
    ok = x.notna() & y.notna() & np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return
    xcap = safe_quantile(x[ok], 0.99)
    ycap = safe_quantile(y[ok], 0.99)
    show = ok & (x <= xcap) & (y <= ycap)
    fig, ax = plt.subplots(figsize=(7.5, 6))
    ax.scatter(x[show], y[show], s=12, alpha=0.35)
    ax.set_title("Recorded activity rate vs resolved location-change rate")
    ax.set_xlabel("Recorded events per hour")
    ax.set_ylabel("Resolved location changes per hour")
    ax.grid(alpha=0.2)
    ax.text(
        0.99,
        0.02,
        "Display capped at 99th percentile on both axes",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_coverage(df: pd.DataFrame, path: Path):
    x = pd.to_numeric(df["resolved_event_coverage"], errors="coerce").dropna() * 100
    if x.empty:
        return
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.hist(x, bins=np.linspace(0, 100, 41))
    ax.set_title("Resolved spatial-event coverage across shifts")
    ax.set_xlabel("Percentage of shift events with a resolved room/door-point")
    ax.set_ylabel("Number of rostered shifts")
    ax.set_xlim(0, 100)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def export_summary(
    df: pd.DataFrame,
    con: duckdb.DuckDBPyConnection,
    outdir: Path,
    crosswalk: Path | None,
):
    def med(col):
        x = pd.to_numeric(df[col], errors="coerce").dropna()
        return float(x.median()) if not x.empty else np.nan

    overlap_count = con.execute("""
        with x as (
            select staff, shift_start,
                   lag(shift_end) over(partition by staff order by shift_start, shift_end) as prev_end
            from roster_intervals
        )
        select count(*) from x where prev_end is not null and shift_start <= prev_end
    """).fetchone()[0]

    summary = pd.DataFrame(
        [
            {"metric": "rostered_shifts_with_activity", "value": len(df)},
            {
                "metric": "median_shift_duration_hours",
                "value": med("shift_duration_hours"),
            },
            {"metric": "median_events_per_shift", "value": med("total_events")},
            {"metric": "median_events_per_hour", "value": med("events_per_hour")},
            {
                "metric": "median_distinct_resolved_locations",
                "value": med("distinct_resolved_locations"),
            },
            {
                "metric": "median_location_changes_per_hour",
                "value": med("location_changes_per_hour"),
            },
            {
                "metric": "median_resolved_event_coverage",
                "value": med("resolved_event_coverage"),
            },
            {"metric": "roster_interval_overlaps_detected", "value": overlap_count},
            {
                "metric": "workstation_crosswalk_used",
                "value": str(crosswalk) if crosswalk and crosswalk.exists() else "none",
            },
        ]
    )
    summary.to_csv(outdir / "activity_exploration_summary.csv", index=False)
    return summary


def write_index(outdir: Path, db_path: Path, crosswalk: Path | None, top_n: int):
    text = f"""AMR-HUB activity exploration

Database: {db_path}
Workstation crosswalk: {crosswalk if crosswalk and crosswalk.exists() else "none"}

Figures
  01_events_per_hour.png                       activity events per rostered hour
  02_activity_composition_per_shift.png        share of FS / WS / Door per shift
  03_distinct_resolved_locations_per_shift.png
  04_location_changes_per_hour.png             A->A repeats not counted
  05_class_transition_probabilities.png
  06_location_transition_probabilities_top{top_n}.png   re-normalised within top {top_n}
  07_resolved_event_coverage.png
  08_events_vs_location_changes.png

CSV
  shift_activity_features.csv                  one row per shift
  class_transition_counts.csv
  class_transition_probabilities.csv
  class_transition_probability_matrix.csv
  per_shift_class_transition_probabilities_long.csv
  per_shift_class_transition_features.csv
  location_transition_counts.csv               changes only
  location_transition_probabilities.csv
  location_transition_probability_matrix_top{top_n}.csv
  top{top_n}_transition_locations.csv
  activity_exploration_summary.csv

Notes
  - Workstations are resolved only where the crosswalk has a room.
  - Door points identify the door, not direction of travel.
  - Events inside overlapping roster intervals are counted in each; see
    roster_interval_overlaps_detected in the summary.
"""
    (outdir / "REPORT_INDEX.txt").write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="AMR-HUB pre-clustering activity exploration"
    )
    parser.add_argument(
        "--db", default=None, help="DuckDB filename in /data, or absolute path"
    )
    parser.add_argument(
        "--out", default="/outputs/activity_exploration", help="Output directory"
    )
    parser.add_argument(
        "--crosswalk",
        default=None,
        help="Workstation crosswalk CSV; defaults to /outputs/ws_crosswalk.csv when present",
    )
    parser.add_argument(
        "--top-locations",
        type=int,
        default=DEFAULT_TOP_LOCATIONS,
        help="Number of locations shown in transition heatmap",
    )
    args = parser.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    db_path = find_database(args.db)
    crosswalk = (
        Path(args.crosswalk) if args.crosswalk else Path("/outputs/ws_crosswalk.csv")
    )
    if not crosswalk.exists():
        crosswalk = None

    print(f"[db] {db_path}")
    print(f"[out] {outdir}")
    print(f"[crosswalk] {crosswalk if crosswalk else 'none'}")

    con = connect_database(db_path)
    try:
        locmap = build_location_map(con, crosswalk)
        locmap.to_csv(outdir / "spatial_location_map_used.csv", index=False)
        create_analysis_tables(con, locmap)

        shifts = export_shift_features(con, outdir)
        class_counts, class_matrix = export_class_transitions(con, outdir)
        loc_counts, loc_matrix = export_location_transitions(
            con, outdir, args.top_locations
        )
        summary = export_summary(shifts, con, outdir, crosswalk)

        save_hist(
            shifts["events_per_hour"],
            "Recorded activity events per hour across rostered shifts",
            "Recorded non-roster events per hour",
            outdir / "01_events_per_hour.png",
        )
        plot_activity_composition(
            shifts, outdir / "02_activity_composition_per_shift.png"
        )
        save_hist(
            shifts["distinct_resolved_locations"],
            "Distinct resolved spatial locations per rostered shift",
            "Distinct resolved rooms / door-points",
            outdir / "03_distinct_resolved_locations_per_shift.png",
            bins=30,
        )
        save_hist(
            shifts["location_changes_per_hour"],
            "Resolved location changes per hour across rostered shifts",
            "Resolved location changes per hour",
            outdir / "04_location_changes_per_hour.png",
        )
        plot_heatmap(
            class_matrix,
            "Event-class transition probabilities",
            outdir / "05_class_transition_probabilities.png",
            annotate=True,
        )
        plot_heatmap(
            loc_matrix,
            f"Resolved-location change probabilities, top {args.top_locations} locations",
            outdir
            / f"06_location_transition_probabilities_top{args.top_locations}.png",
            annotate=False,
        )
        plot_coverage(shifts, outdir / "07_resolved_event_coverage.png")
        plot_scatter(shifts, outdir / "08_events_vs_location_changes.png")

        write_index(outdir, db_path, crosswalk, args.top_locations)

        print("\n=== COMPLETE ===")
        print(summary.to_string(index=False))
        print(f"\nSaved outputs to: {outdir}")
        print("No clustering or prediction model was fitted.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
