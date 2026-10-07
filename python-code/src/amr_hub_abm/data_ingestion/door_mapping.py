"""Map DuckDB door reference records to door point codes."""

from __future__ import annotations

import re

import duckdb
import pandas as pd

from amr_hub_abm.config import (
    LocationTimeseriesDataConfig,
    LocationTimeseriesDataFormat,
)
from amr_hub_abm.exceptions import LocationDataValidationError
from amr_hub_abm.location_data import (
    TABLE_NAME_PATTERN,
    LocationDataValidationReport,
    _column_errors,
    _is_missing,
)

DOOR_REFERENCE_SCHEMA = "Ref"
DOOR_REFERENCE_TABLE = "Door"
DOOR_REFERENCE_COLUMNS = ("DoorKey", "DoorName")
DOOR_CODE_PATTERN = re.compile(r"\b(?:E\d{2})?[A-Z]{2}\d{2,3}[A-Z]?\b")
DOOR_MAPPING_COLUMNS = ("door_id", "door_name", "door_code", "door_point", "matched")


def read_door_mapping(source: LocationTimeseriesDataConfig) -> pd.DataFrame:
    """
    Read the DuckDB door reference table and match each door to a code.

    Takes the same config as ``read_location_timeseries``; only ``path`` and
    ``format`` are used. ``door_id`` is the reference table's DoorKey, typed
    like the canonical ``door_id`` column. ``door_point`` is
    ``doorpoint:CODE#DOORKEY:n`` for doors whose name contains a code.
    """
    if not source.path.exists():
        msg = f"Door reference data file not found: {source.path}"
        raise FileNotFoundError(msg)
    if source.format != LocationTimeseriesDataFormat.DUCKDB:
        msg = "Door reference data can only be read from a DuckDB source."
        raise LocationDataValidationError((msg,))

    errors: list[str] = []
    try:
        with duckdb.connect(str(source.path), read_only=True) as connection:
            _validate_door_reference_columns(connection, errors)
            LocationDataValidationReport(tuple(errors)).raise_for_errors()

            selected_columns = ", ".join(DOOR_REFERENCE_COLUMNS)
            query = (
                f"SELECT {selected_columns} "  # noqa: S608
                f'FROM "{DOOR_REFERENCE_SCHEMA}"."{DOOR_REFERENCE_TABLE}" '
                "WHERE DoorKey IS NOT NULL AND DoorName IS NOT NULL "
                "ORDER BY DoorKey"
            )
            doors = connection.execute(query).fetch_df()
    except LocationDataValidationError:
        raise
    except duckdb.Error as exc:
        msg = f"Could not read DuckDB door reference data: {exc}"
        raise LocationDataValidationError((msg,)) from exc

    mapping = _build_door_mapping(doors)
    _validate_door_mapping(mapping).raise_for_errors()
    return mapping


def _validate_door_reference_columns(
    connection: duckdb.DuckDBPyConnection,
    errors: list[str],
) -> None:
    """Validate that the door reference table exists with its required columns."""
    errors.extend(
        f"Invalid DuckDB schema or table name: {name!r}"
        for name in (DOOR_REFERENCE_SCHEMA, DOOR_REFERENCE_TABLE)
        if TABLE_NAME_PATTERN.fullmatch(name) is None
    )
    if errors:
        return

    rows = connection.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = ? AND table_name = ? "
        "ORDER BY ordinal_position",
        [DOOR_REFERENCE_SCHEMA, DOOR_REFERENCE_TABLE],
    ).fetchall()
    if not rows:
        errors.append(
            f"DuckDB table or view '{DOOR_REFERENCE_TABLE}' does not exist "
            f"in schema '{DOOR_REFERENCE_SCHEMA}'."
        )
        return

    # Only the required columns are checked; extra reference columns are allowed.
    actual = [str(name) for (name,) in rows if name in DOOR_REFERENCE_COLUMNS]
    errors.extend(_column_errors(actual, DOOR_REFERENCE_COLUMNS))


def _build_door_mapping(doors: pd.DataFrame) -> pd.DataFrame:
    """Turn raw DoorKey/DoorName rows into the door mapping."""
    door_ids = pd.to_numeric(doors["DoorKey"], errors="coerce")
    door_ids = door_ids.where(door_ids.isna() | door_ids.mod(1).eq(0)).astype("Int64")
    door_names = doors["DoorName"].astype("string")
    codes = door_names.map(_extract_door_code).astype("string")
    matched = codes.notna()

    door_points = pd.Series(pd.NA, index=doors.index, dtype="string")
    door_points[matched] = (
        "doorpoint:" + codes[matched] + "#DOORKEY:" + door_ids[matched].astype("string")
    )

    return pd.DataFrame(
        {
            "door_id": door_ids,
            "door_name": door_names,
            "door_code": codes,
            "door_point": door_points,
            "matched": matched.astype(bool),
        },
        columns=list(DOOR_MAPPING_COLUMNS),
    ).reset_index(drop=True)


def _extract_door_code(value: object) -> str | None:
    """Return the first door code in a door name, or None if there is none."""
    if _is_missing(value):
        return None
    name = re.sub(r"\s+", " ", str(value).strip()).upper()
    match = DOOR_CODE_PATTERN.search(name)
    return match.group(0) if match else None


def _validate_door_mapping(mapping: pd.DataFrame) -> LocationDataValidationReport:
    """Collect structural errors and unmatched-door warnings for a door mapping."""
    errors = _column_errors(mapping.columns, DOOR_MAPPING_COLUMNS)
    if errors:
        return LocationDataValidationReport(tuple(errors))
    if mapping.empty:
        return LocationDataValidationReport(("Door reference table is empty.",))

    door_ids = mapping["door_id"]
    if door_ids.isna().any():
        errors.append("Door ids must not be null or invalid.")
    if (door_ids.dropna() <= 0).any():
        errors.append("Door ids must be positive integers.")
    errors.extend(
        f"Door {int(door_id)}: door_id is duplicated."
        for door_id in sorted(door_ids[door_ids.duplicated()].dropna().unique())
    )

    warnings = [
        f"Door {int(row.door_id)}: no door code found in {row.door_name!r}."
        for row in mapping.loc[~mapping["matched"]].itertuples(index=False)
        if not _is_missing(row.door_id)
    ]
    return LocationDataValidationReport(tuple(errors), tuple(warnings))
