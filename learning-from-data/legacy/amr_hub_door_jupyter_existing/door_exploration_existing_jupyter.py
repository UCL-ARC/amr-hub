#!/usr/bin/env python3
"""AMR-HUB door exploration: door messages per rostered shift and door-to-door episodes.

Uses only duckdb, pandas and numpy (available in the existing Jupyter image); figures
are written as SVG. A Door Message is treated as a door interaction, not a verified
physical pass.
"""

from __future__ import annotations

import argparse
import html
import math
import re
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

DEFAULT_DATA_DIR = Path("/data")
DEFAULT_OUTPUT_DIR = Path("/outputs/door_exploration")
DOOR_CODE_RE = re.compile(r"\b(?:E\d{2})?[A-Z]{2}\d{2,3}[A-Z]?\b", re.IGNORECASE)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sql_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def find_database(db_arg: str | None, data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    if db_arg:
        candidate = Path(db_arg)
        if candidate.is_file():
            return candidate.resolve()
        under_data = data_dir / db_arg
        if under_data.is_file():
            return under_data.resolve()
        raise FileNotFoundError(f"Database not found: {db_arg!r}")

    matches = sorted({*data_dir.glob("*.db"), *data_dir.glob("*.duckdb")})
    if not matches:
        raise FileNotFoundError(f"No .db or .duckdb file found in {data_dir}")
    if len(matches) > 1:
        names = "\n".join(f"  - {p.name}" for p in matches)
        raise RuntimeError(
            "Multiple databases found. Set DB_NAME to one filename:\n" + names
        )
    return matches[0].resolve()


def connect_database(db_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH {sql_string(db_path)} AS {quote_ident('output')} (READ_ONLY)")
    con.execute("USE output")
    return con


def require_tables(con: duckdb.DuckDBPyConnection) -> None:
    required = [
        ("Data", "StaffLocationEvent"),
        ("Ref", "InteractionType"),
        ("Ref", "Roster"),
        ("Ref", "Staff"),
        ("Ref", "Door"),
    ]
    missing = []
    for schema, table in required:
        n = con.execute(
            """
            select count(*)
            from information_schema.tables
            where lower(table_schema)=lower(?)
              and lower(table_name)=lower(?)
            """,
            [schema, table],
        ).fetchone()[0]
        if not n:
            missing.append(f"{schema}.{table}")
    if missing:
        raise RuntimeError("Missing required database objects: " + ", ".join(missing))


def standardise_door_label(door_key: Any, door_name: Any) -> str:
    if door_key is None or pd.isna(door_key):
        return "UNKNOWN_DOOR"
    key = int(door_key)
    name = (
        ""
        if door_name is None or pd.isna(door_name)
        else str(door_name).strip().upper()
    )
    match = DOOR_CODE_RE.search(name)
    if match:
        return f"{match.group(0).upper()} [D{key}]"
    return f"DOORKEY:{key}"


def create_valid_shifts(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("DROP TABLE IF EXISTS valid_shifts")
    con.execute(
        """
        CREATE TEMP TABLE valid_shifts AS
        WITH roster_pairs AS (
            SELECT
                CAST(e.MasterIndexId AS VARCHAR) AS staff,
                CAST(e.LinkKey AS BIGINT) AS link_key,
                MIN(CASE WHEN it.InteractionType = 'Roster Start'
                         THEN e.EventDateTime END) AS shift_start,
                MAX(CASE WHEN it.InteractionType = 'Roster End'
                         THEN e.EventDateTime END) AS shift_end,
                MAX(CASE WHEN it.InteractionType = 'Roster Start'
                         THEN e.SourceKey END) AS roster_key
            FROM Data.StaffLocationEvent e
            JOIN Ref.InteractionType it
              ON e.InteractionTypeKey = it.InteractionTypeKey
            WHERE it.InteractionTypeClass = 'Roster'
              AND e.LinkKey IS NOT NULL
            GROUP BY e.MasterIndexId, e.LinkKey
        )
        SELECT
            p.staff,
            p.link_key,
            p.shift_start,
            p.shift_end,
            p.roster_key,
            COALESCE(CAST(r.RosterName AS VARCHAR), 'unknown') AS roster_unit,
            (epoch(p.shift_end) - epoch(p.shift_start)) / 3600.0 AS duration_hours
        FROM roster_pairs p
        LEFT JOIN Ref.Roster r
          ON p.roster_key = r.RosterKey
        WHERE p.shift_start IS NOT NULL
          AND p.shift_end IS NOT NULL
          AND p.shift_end > p.shift_start
        """
    )


def load_shift_base(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT
            v.staff,
            v.link_key,
            v.shift_start,
            v.shift_end,
            v.roster_unit,
            v.duration_hours,
            COALESCE(CAST(s.Role AS VARCHAR), 'unknown') AS role,
            COUNT(e.EventDateTime) FILTER (
                WHERE it.InteractionTypeClass <> 'Roster'
            ) AS activity_events
        FROM valid_shifts v
        LEFT JOIN Ref.Staff s
          ON CAST(s.MasterIndexId AS VARCHAR) = v.staff
        LEFT JOIN Data.StaffLocationEvent e
          ON CAST(e.MasterIndexId AS VARCHAR) = v.staff
         AND e.EventDateTime BETWEEN v.shift_start AND v.shift_end
        LEFT JOIN Ref.InteractionType it
          ON e.InteractionTypeKey = it.InteractionTypeKey
        GROUP BY
            v.staff, v.link_key, v.shift_start, v.shift_end,
            v.roster_unit, v.duration_hours, role
        ORDER BY v.shift_start, v.staff, v.link_key
        """
    ).df()


def load_raw_door_events(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT
            v.staff,
            v.link_key,
            v.roster_unit,
            e.EventDateTime AS event_time,
            e.SourceKey AS door_key,
            d.DoorName AS door_name
        FROM valid_shifts v
        JOIN Data.StaffLocationEvent e
          ON CAST(e.MasterIndexId AS VARCHAR) = v.staff
         AND e.EventDateTime BETWEEN v.shift_start AND v.shift_end
        JOIN Ref.InteractionType it
          ON e.InteractionTypeKey = it.InteractionTypeKey
        LEFT JOIN Ref.Door d
          ON e.SourceKey = d.DoorKey
        WHERE it.InteractionTypeClass = 'Door Message'
        ORDER BY v.staff, v.link_key, e.EventDateTime
        """
    ).df()


def dedupe_door_events(frame: pd.DataFrame, seconds: float) -> pd.DataFrame:
    if frame.empty or seconds <= 0:
        return frame.copy()
    rows = []
    for _, group in frame.groupby(["staff", "link_key"], sort=False):
        previous_key = None
        previous_time = None
        for _, row in group.sort_values("event_time").iterrows():
            key = None if pd.isna(row["door_key"]) else int(row["door_key"])
            time = pd.Timestamp(row["event_time"])
            repeated = (
                previous_time is not None
                and key == previous_key
                and (time - previous_time).total_seconds() <= seconds
            )
            if not repeated:
                rows.append(row)
                previous_key, previous_time = key, time
    return pd.DataFrame(rows).reset_index(drop=True) if rows else frame.iloc[0:0].copy()


def build_shift_activity(shift_base: pd.DataFrame, door_events: pd.DataFrame):
    shifts = (
        shift_base.sort_values(["shift_start", "staff", "link_key"])
        .reset_index(drop=True)
        .copy()
    )
    shifts["shift_id"] = [f"shift_{i:06d}" for i in range(1, len(shifts) + 1)]
    lookup = {
        (str(r.staff), int(r.link_key)): str(r.shift_id)
        for r in shifts.itertuples(index=False)
    }

    if door_events.empty:
        counts = pd.DataFrame(
            columns=["staff", "link_key", "door_interactions", "distinct_doors"]
        )
    else:
        counts = door_events.groupby(["staff", "link_key"], as_index=False).agg(
            door_interactions=("event_time", "size"),
            distinct_doors=("door_key", "nunique"),
        )
    shifts = shifts.merge(counts, on=["staff", "link_key"], how="left")
    shifts["door_interactions"] = shifts["door_interactions"].fillna(0).astype(int)
    shifts["distinct_doors"] = shifts["distinct_doors"].fillna(0).astype(int)
    shifts["door_interactions_per_hour"] = np.where(
        shifts["duration_hours"] > 0,
        shifts["door_interactions"] / shifts["duration_hours"],
        np.nan,
    )
    shifts["shift_start_hour"] = pd.to_datetime(shifts["shift_start"]).dt.hour
    return shifts, lookup


def build_episodes(door_events: pd.DataFrame, shift_lookup) -> pd.DataFrame:
    rows = []
    n = 0
    for (staff, link_key), group in door_events.groupby(
        ["staff", "link_key"], sort=False
    ):
        group = group.sort_values("event_time").reset_index(drop=True)
        for i in range(len(group) - 1):
            a, b = group.iloc[i], group.iloc[i + 1]
            t0, t1 = pd.Timestamp(a["event_time"]), pd.Timestamp(b["event_time"])
            if t1 < t0:
                continue
            n += 1
            rows.append(
                {
                    "episode_row": n,
                    "episode_id": f"episode_{n:07d}",
                    "shift_id": shift_lookup.get((str(staff), int(link_key))),
                    "staff": str(staff),
                    "link_key": int(link_key),
                    "roster_unit": str(a["roster_unit"]),
                    "start_time": t0,
                    "end_time": t1,
                    "start_hour": int(t0.hour),
                    "start_door": standardise_door_label(a["door_key"], a["door_name"]),
                    "end_door": standardise_door_label(b["door_key"], b["door_name"]),
                    "duration_min": (t1 - t0).total_seconds() / 60.0,
                }
            )
    return pd.DataFrame(rows)


def add_episode_activity_counts(
    con: duckdb.DuckDBPyConnection, episodes: pd.DataFrame
) -> pd.DataFrame:
    if episodes.empty:
        for c in [
            "events_between",
            "flowsheet_events_between",
            "workstation_events_between",
        ]:
            episodes[c] = pd.Series(dtype="int64")
        return episodes
    internal = episodes[["episode_row", "staff", "start_time", "end_time"]].copy()
    con.register("episode_input", internal)
    counts = con.execute(
        """
        SELECT
            ep.episode_row,
            COUNT(e.EventDateTime) FILTER (
                WHERE it.InteractionTypeClass NOT IN ('Roster', 'Door Message')
            ) AS events_between,
            COUNT(e.EventDateTime) FILTER (
                WHERE it.InteractionTypeClass = 'Flowsheet'
            ) AS flowsheet_events_between,
            COUNT(e.EventDateTime) FILTER (
                WHERE it.InteractionTypeClass = 'Workstation'
            ) AS workstation_events_between
        FROM episode_input ep
        LEFT JOIN Data.StaffLocationEvent e
          ON CAST(e.MasterIndexId AS VARCHAR) = ep.staff
         AND e.EventDateTime > ep.start_time
         AND e.EventDateTime < ep.end_time
        LEFT JOIN Ref.InteractionType it
          ON e.InteractionTypeKey = it.InteractionTypeKey
        GROUP BY ep.episode_row
        ORDER BY ep.episode_row
        """
    ).df()
    con.unregister("episode_input")
    out = episodes.merge(counts, on="episode_row", how="left")
    for c in [
        "events_between",
        "flowsheet_events_between",
        "workstation_events_between",
    ]:
        out[c] = out[c].fillna(0).astype(int)
    return out


def _svg_text(x, y, text, size=13, anchor="start", weight="normal", rotate=None):
    transform = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
        f'font-family="Arial, sans-serif" font-weight="{weight}" fill="#222"{transform}>'
        f"{html.escape(str(text))}</text>"
    )


def _write_svg(path: Path, body: str, width=1000, height=620):
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">'
        '<rect width="100%" height="100%" fill="white"/>' + body + "</svg>"
    )
    path.write_text(svg, encoding="utf-8")


def _finite(series: pd.Series) -> np.ndarray:
    a = (
        pd.to_numeric(series, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .to_numpy(dtype=float)
    )
    return a[np.isfinite(a)]


def _hist_data(series: pd.Series, integer=False, bins=36):
    data = _finite(series)
    if len(data) == 0:
        return data, np.array([]), np.array([]), None, 0
    q99 = float(np.quantile(data, 0.99))
    maxv = float(np.max(data))
    cap = q99 if q99 > 0 and maxv > q99 * 1.15 else None
    shown = data if cap is None else data[data <= cap]
    tail = 0 if cap is None else int(np.sum(data > cap))
    if integer and shown.size and np.max(shown) <= 100:
        lo = int(math.floor(np.min(shown)))
        hi = int(math.ceil(np.max(shown)))
        edges = np.arange(lo - 0.5, hi + 1.5, 1.0)
        if len(edges) < 2:
            edges = np.array([-0.5, 0.5])
    else:
        edges = np.histogram_bin_edges(
            shown, bins=min(bins, max(8, int(np.sqrt(len(shown)))))
        )
    counts, edges = np.histogram(shown, bins=edges)
    return shown, counts, edges, cap, tail


def save_histogram_svg(series, title, xlabel, path, integer=False):
    _, counts, edges, cap, tail = _hist_data(series, integer=integer)
    W, H = 1000, 620
    left, right, top, bottom = 90, 35, 70, 85
    pw, ph = W - left - right, H - top - bottom
    parts = [_svg_text(W / 2, 34, title, 20, "middle", "bold")]
    if len(counts) == 0:
        parts.append(_svg_text(W / 2, H / 2, "No data available", 18, "middle"))
        _write_svg(path, "".join(parts), W, H)
        return
    ymax = max(1, int(counts.max()))
    parts += [
        f'<line x1="{left}" y1="{top + ph}" x2="{left + pw}" y2="{top + ph}" stroke="#444"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + ph}" stroke="#444"/>',
    ]
    bw = pw / len(counts)
    for i, c in enumerate(counts):
        h = ph * c / ymax
        x = left + i * bw + 1
        y = top + ph - h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(1, bw - 2):.1f}" height="{h:.1f}" fill="#5b7fa3" opacity="0.82"/>'
        )
    for frac in [0, 0.25, 0.5, 0.75, 1]:
        y = top + ph * (1 - frac)
        val = int(round(ymax * frac))
        parts.append(
            f'<line x1="{left - 5}" y1="{y:.1f}" x2="{left + pw}" y2="{y:.1f}" stroke="#dddddd"/>'
        )
        parts.append(_svg_text(left - 10, y + 4, f"{val:,}", 11, "end"))
    xmin, xmax = float(edges[0]), float(edges[-1])
    for frac in [0, 0.25, 0.5, 0.75, 1]:
        x = left + pw * frac
        v = xmin + (xmax - xmin) * frac
        label = f"{v:.0f}" if integer else f"{v:.2g}"
        parts.append(_svg_text(x, top + ph + 25, label, 11, "middle"))
    parts.append(_svg_text(left + pw / 2, H - 24, xlabel, 14, "middle"))
    parts.append(
        _svg_text(24, top + ph / 2, "Number of observations", 14, "middle", rotate=-90)
    )
    if cap is not None:
        parts.append(
            _svg_text(
                left + pw,
                56,
                f"Display ≤99th percentile ({cap:.2f}); {tail:,} larger values remain in CSV",
                11,
                "end",
            )
        )
    _write_svg(path, "".join(parts), W, H)


def save_scatter_svg(shifts: pd.DataFrame, path: Path):
    W, H = 1000, 620
    left, right, top, bottom = 90, 35, 70, 85
    pw, ph = W - left - right, H - top - bottom
    parts = [
        _svg_text(
            W / 2,
            34,
            "Door interactions vs rostered shift duration",
            20,
            "middle",
            "bold",
        )
    ]
    df = (
        shifts[["duration_hours", "door_interactions"]]
        .apply(pd.to_numeric, errors="coerce")
        .dropna()
    )
    if df.empty:
        parts.append(_svg_text(W / 2, H / 2, "No data available", 18, "middle"))
        _write_svg(path, "".join(parts), W, H)
        return
    xcap = float(df["duration_hours"].quantile(0.99))
    ycap = float(df["door_interactions"].quantile(0.99))
    plot = df[(df["duration_hours"] <= xcap) & (df["door_interactions"] <= ycap)]
    xmin, xmax = 0.0, max(1.0, xcap)
    ymin, ymax = 0.0, max(1.0, ycap)
    parts += [
        f'<line x1="{left}" y1="{top + ph}" x2="{left + pw}" y2="{top + ph}" stroke="#444"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + ph}" stroke="#444"/>',
    ]
    for frac in [0, 0.25, 0.5, 0.75, 1]:
        x = left + pw * frac
        xv = xmin + (xmax - xmin) * frac
        y = top + ph * (1 - frac)
        yv = ymin + (ymax - ymin) * frac
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + pw}" y2="{y:.1f}" stroke="#eeeeee"/>'
        )
        parts.append(_svg_text(x, top + ph + 25, f"{xv:.1f}", 11, "middle"))
        parts.append(_svg_text(left - 10, y + 4, f"{yv:.0f}", 11, "end"))
    for r in plot.itertuples(index=False):
        x = left + pw * (float(r.duration_hours) - xmin) / (xmax - xmin)
        y = top + ph * (1 - (float(r.door_interactions) - ymin) / (ymax - ymin))
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="#5b7fa3" opacity="0.28"/>'
        )
    parts.append(
        _svg_text(left + pw / 2, H - 24, "Shift duration (hours)", 14, "middle")
    )
    parts.append(
        _svg_text(
            24, top + ph / 2, "Door interactions in shift", 14, "middle", rotate=-90
        )
    )
    parts.append(
        _svg_text(
            left + pw,
            56,
            "Display limited to the 99th percentile on each axis",
            11,
            "end",
        )
    )
    _write_svg(path, "".join(parts), W, H)


def save_transition_matrix_svg(matrix: pd.DataFrame, path: Path):
    labels = list(matrix.index)
    n = len(labels)
    W = max(920, 125 + 62 * n)
    H = max(760, 160 + 52 * n)
    left, top, right, bottom = 180, 90, 45, 150
    pw, ph = W - left - right, H - top - bottom
    parts = [
        _svg_text(
            W / 2,
            34,
            "Consecutive door-interaction transition matrix",
            20,
            "middle",
            "bold",
        )
    ]
    if matrix.empty:
        parts.append(
            _svg_text(W / 2, H / 2, "No door-to-door episodes available", 18, "middle")
        )
        _write_svg(path, "".join(parts), W, H)
        return
    vals = matrix.to_numpy(dtype=float)
    vmax = max(1.0, float(vals.max()))
    cw, ch = pw / n, ph / n
    for i, rowlab in enumerate(labels):
        parts.append(_svg_text(left - 8, top + (i + 0.5) * ch + 4, rowlab, 10, "end"))
        parts.append(
            _svg_text(
                left + (i + 0.5) * cw, top + ph + 12, rowlab, 10, "end", rotate=-55
            )
        )
        for j in range(n):
            v = vals[i, j]
            t = math.sqrt(v / vmax) if vmax else 0
            r = int(245 - 155 * t)
            g = int(248 - 130 * t)
            b = int(250 - 90 * t)
            x, y = left + j * cw, top + i * ch
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cw:.1f}" height="{ch:.1f}" fill="rgb({r},{g},{b})" stroke="#ffffff"/>'
            )
            if v > 0:
                color = "white" if t > 0.55 else "#222"
                parts.append(
                    f'<text x="{x + cw / 2:.1f}" y="{y + ch / 2 + 4:.1f}" font-size="9" text-anchor="middle" font-family="Arial, sans-serif" fill="{color}">{int(v):,}</text>'
                )
    parts.append(
        _svg_text(left + pw / 2, H - 20, "Next door interaction", 14, "middle")
    )
    parts.append(
        _svg_text(
            24, top + ph / 2, "Current door interaction", 14, "middle", rotate=-90
        )
    )
    _write_svg(path, "".join(parts), W, H)


def make_summary(shifts, episodes, dedupe_seconds):
    def med(df, col):
        if df.empty or col not in df:
            return None
        x = pd.to_numeric(df[col], errors="coerce").median()
        return None if pd.isna(x) else round(float(x), 3)

    return pd.DataFrame(
        [
            ("Valid rostered shifts", len(shifts)),
            (
                "Shifts with zero door interactions",
                int((shifts["door_interactions"] == 0).sum())
                if not shifts.empty
                else 0,
            ),
            (
                "Shifts with at least one door interaction",
                int((shifts["door_interactions"] > 0).sum()) if not shifts.empty else 0,
            ),
            ("Median door interactions per shift", med(shifts, "door_interactions")),
            (
                "Median door interactions per hour",
                med(shifts, "door_interactions_per_hour"),
            ),
            ("Door-to-door episodes", len(episodes)),
            ("Median minutes between doors", med(episodes, "duration_min")),
            (
                "Median recorded activities between doors",
                med(episodes, "events_between"),
            ),
            (
                "Same-door return episodes",
                int((episodes["start_door"] == episodes["end_door"]).sum())
                if not episodes.empty
                else 0,
            ),
            ("Door-message deduplication window (seconds)", dedupe_seconds),
        ],
        columns=["metric", "value"],
    )


def run_exploration(
    db: str | None = None,
    out: str | Path = DEFAULT_OUTPUT_DIR,
    dedupe_seconds: float = 0.0,
):
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = find_database(db)
    print(f"[door-explore] database: {db_path}")
    print(f"[door-explore] output:   {out_dir}")
    print(f"[door-explore] dedupe:   {dedupe_seconds:g} seconds")

    con = connect_database(db_path)
    require_tables(con)
    create_valid_shifts(con)
    shift_base = load_shift_base(con)
    raw_doors = load_raw_door_events(con)
    print(f"[door-explore] raw rostered Door Message records: {len(raw_doors):,}")
    doors = dedupe_door_events(raw_doors, dedupe_seconds)
    shifts_internal, shift_lookup = build_shift_activity(shift_base, doors)
    episodes_internal = add_episode_activity_counts(
        con, build_episodes(doors, shift_lookup)
    )

    role_map = dict(zip(shifts_internal["shift_id"], shifts_internal["role"]))
    if not episodes_internal.empty:
        episodes_internal["role"] = (
            episodes_internal["shift_id"].map(role_map).fillna("unknown")
        )

    shift_export = shifts_internal[
        [
            "shift_id",
            "roster_unit",
            "role",
            "duration_hours",
            "shift_start_hour",
            "activity_events",
            "door_interactions",
            "door_interactions_per_hour",
            "distinct_doors",
        ]
    ].copy()
    shift_export["duration_hours"] = shift_export["duration_hours"].round(3)
    shift_export["door_interactions_per_hour"] = shift_export[
        "door_interactions_per_hour"
    ].round(4)

    episode_cols = [
        "episode_id",
        "shift_id",
        "roster_unit",
        "role",
        "start_hour",
        "start_door",
        "end_door",
        "duration_min",
        "events_between",
        "flowsheet_events_between",
        "workstation_events_between",
    ]
    episode_export = (
        pd.DataFrame(columns=episode_cols)
        if episodes_internal.empty
        else episodes_internal[episode_cols].copy()
    )
    if not episode_export.empty:
        episode_export["duration_min"] = episode_export["duration_min"].round(3)

    if doors.empty:
        door_counts = pd.DataFrame(columns=["door", "door_interactions"])
    else:
        temp = doors.copy()
        temp["door"] = [
            standardise_door_label(k, n)
            for k, n in zip(temp["door_key"], temp["door_name"])
        ]
        door_counts = (
            temp.groupby("door", as_index=False)
            .size()
            .rename(columns={"size": "door_interactions"})
            .sort_values("door_interactions", ascending=False)
        )

    if episode_export.empty:
        transition_matrix = pd.DataFrame()
    else:
        labels = sorted(
            set(episode_export["start_door"]) | set(episode_export["end_door"])
        )
        transition_matrix = pd.crosstab(
            episode_export["start_door"], episode_export["end_door"]
        ).reindex(index=labels, columns=labels, fill_value=0)

    summary = make_summary(shift_export, episode_export, dedupe_seconds)
    shift_export.to_csv(out_dir / "shift_door_activity.csv", index=False)
    episode_export.to_csv(out_dir / "door_episodes.csv", index=False)
    door_counts.to_csv(out_dir / "door_counts.csv", index=False)
    transition_matrix.to_csv(out_dir / "door_transition_matrix.csv")
    summary.to_csv(out_dir / "door_exploration_summary.csv", index=False)

    figures = {
        "01": out_dir / "01_door_interactions_per_shift.svg",
        "02": out_dir / "02_door_interactions_per_hour.svg",
        "03": out_dir / "03_door_interactions_vs_shift_duration.svg",
        "04": out_dir / "04_minutes_between_door_interactions.svg",
        "05": out_dir / "05_activities_between_doors.svg",
        "06": out_dir / "06_door_transition_matrix.svg",
    }
    save_histogram_svg(
        shift_export["door_interactions"],
        "Door interactions per rostered shift",
        "Door Message interactions in shift",
        figures["01"],
        integer=True,
    )
    save_histogram_svg(
        shift_export["door_interactions_per_hour"],
        "Door interactions per hour of rostered shift",
        "Door interactions per rostered hour",
        figures["02"],
    )
    save_scatter_svg(shift_export, figures["03"])
    save_histogram_svg(
        episode_export.get("duration_min", pd.Series(dtype=float)),
        "Time between consecutive door interactions",
        "Minutes between consecutive door interactions",
        figures["04"],
    )
    save_histogram_svg(
        episode_export.get("events_between", pd.Series(dtype=float)),
        "Recorded activities between consecutive door interactions",
        "Non-door activity events between doors",
        figures["05"],
        integer=True,
    )
    save_transition_matrix_svg(transition_matrix, figures["06"])

    (out_dir / "REPORT_INDEX.txt").write_text(
        "AMR-HUB door exploration\n\n"
        "Door Message is treated as a door interaction, not a verified physical pass.\n\n"
        "CSVs: shift_door_activity.csv, door_episodes.csv, door_counts.csv, door_transition_matrix.csv, door_exploration_summary.csv\n"
        "Figures: 01-06 SVG files in this folder.\n",
        encoding="utf-8",
    )
    con.close()
    print(f"[door-explore] complete: {out_dir}")
    return {
        "db_path": db_path,
        "out_dir": out_dir,
        "summary": summary,
        "shifts": shift_export,
        "episodes": episode_export,
        "door_counts": door_counts,
        "transition_matrix": transition_matrix,
        "figures": figures,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--db", default=None, help="DuckDB filename under /data, or explicit path"
    )
    p.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--door-dedupe-seconds", type=float, default=0.0)
    a = p.parse_args()
    run_exploration(a.db, a.out, a.door_dedupe_seconds)


if __name__ == "__main__":
    main()
