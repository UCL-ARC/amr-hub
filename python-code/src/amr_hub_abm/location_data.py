"""Load and validate location-event inputs for the simulation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import duckdb
import pandas as pd

from amr_hub_abm.config import LocationDataConfig, LocationTimeseriesDataFormat
from amr_hub_abm.exceptions import LocationDataValidationError
from amr_hub_abm.spatial.furniture import ContentType

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from amr_hub_abm.spatial.room import Room
    from amr_hub_abm.task.task_duration import TaskDurationConfig

LOCATION_SCHEMA_COMPONENT = "location_timeseries"
LOCATION_SCHEMA_VERSION = 1
DUCKDB_METADATA_TABLE = "amr_hub_schema"

BASE_COLUMNS = (
    "hcw_id",
    "timestamp",
    "location",
    "event_type",
    "patient_id",
    "door_id",
    "content_type",
)
CANONICAL_COLUMNS = ("event_sequence", *BASE_COLUMNS)
DUCKDB_COLUMN_TYPES = {
    "event_sequence": "BIGINT",
    "hcw_id": "INTEGER",
    "timestamp": "TIMESTAMP",
    "location": "VARCHAR",
    "event_type": "VARCHAR",
    "patient_id": "INTEGER",
    "door_id": "INTEGER",
    "content_type": "INTEGER",
}
TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class LocationDataValidationReport:
    """All findings produced by location-event preflight validation."""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def raise_for_errors(self) -> None:
        """Raise one exception containing every validation error."""
        if self.errors:
            raise LocationDataValidationError(self.errors, self.warnings)


def read_location_timeseries(source: LocationDataConfig) -> pd.DataFrame:
    """Read CSV or DuckDB location events into one canonical DataFrame."""
    if not source.path.exists():
        msg = f"Location data file not found: {source.path}"
        raise FileNotFoundError(msg)

    if source.format == LocationTimeseriesDataFormat.CSV:
        data = _read_csv(source.path)
    else:
        data = _read_duckdb(source)

    return _normalise_location_timeseries(data)


def _read_csv(file_path: Path) -> pd.DataFrame:
    """Read the legacy CSV representation without inferring its types."""
    data = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    errors = _column_errors(data.columns, BASE_COLUMNS)
    if errors:
        raise LocationDataValidationError(tuple(errors))

    data = data.loc[:, BASE_COLUMNS].copy()
    data.insert(0, "event_sequence", range(1, len(data) + 1))
    return data


def _read_duckdb(source: LocationDataConfig) -> pd.DataFrame:
    """Read a versioned DuckDB location-event table in read-only mode."""
    if TABLE_NAME_PATTERN.fullmatch(source.table) is None:
        msg = f"Invalid DuckDB table name: {source.table!r}"
        raise LocationDataValidationError((msg,))

    errors: list[str] = []
    if source.schema_version != LOCATION_SCHEMA_VERSION:
        errors.append(
            f"Unsupported location-data schema version {source.schema_version}; "
            f"this release supports version {LOCATION_SCHEMA_VERSION}."
        )
    try:
        with duckdb.connect(str(source.path), read_only=True) as connection:
            _validate_duckdb_metadata(connection, source, errors)
            _validate_duckdb_columns(connection, source.table, errors)
            LocationDataValidationReport(tuple(errors)).raise_for_errors()

            selected_columns = ", ".join(CANONICAL_COLUMNS)
            query = (
                f'SELECT {selected_columns} FROM "{source.table}" '  # noqa: S608
                "ORDER BY hcw_id, timestamp, event_sequence"
            )
            return connection.execute(query).fetch_df()
    except LocationDataValidationError:
        raise
    except duckdb.Error as exc:
        msg = f"Could not read DuckDB location data: {exc}"
        raise LocationDataValidationError((msg,)) from exc


def _validate_duckdb_metadata(
    connection: duckdb.DuckDBPyConnection,
    source: LocationDataConfig,
    errors: list[str],
) -> None:
    """Validate the location-event schema version stored in DuckDB."""
    try:
        row = connection.execute(
            "SELECT schema_version FROM amr_hub_schema WHERE component = ?",
            [LOCATION_SCHEMA_COMPONENT],
        ).fetchone()
    except duckdb.Error:
        errors.append(
            f"Missing or invalid DuckDB metadata table '{DUCKDB_METADATA_TABLE}'."
        )
        return

    if row is None:
        errors.append(
            f"No schema version is registered for '{LOCATION_SCHEMA_COMPONENT}'."
        )
        return

    actual_version = int(row[0])
    if actual_version != source.schema_version:
        errors.append(
            "DuckDB schema version mismatch: "
            f"expected {source.schema_version}, found {actual_version}."
        )


def _validate_duckdb_columns(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    errors: list[str],
) -> None:
    """Validate the exact columns and SQL types of the configured table."""
    rows = connection.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()
    if not rows:
        errors.append(f"DuckDB table '{table}' does not exist in schema 'main'.")
        return

    actual_types = {str(name): str(data_type) for name, data_type in rows}
    errors.extend(_column_errors(actual_types, CANONICAL_COLUMNS))
    for column, expected_type in DUCKDB_COLUMN_TYPES.items():
        actual_type = actual_types.get(column)
        if actual_type is not None and actual_type != expected_type:
            errors.append(
                f"Column '{column}' must be {expected_type}, found {actual_type}."
            )


def _column_errors(
    actual_columns: Iterable[object],
    expected_columns: tuple[str, ...],
) -> list[str]:
    """Return errors for missing and unexpected columns."""
    actual = {str(column) for column in actual_columns}
    expected = set(expected_columns)
    errors = [f"Missing required column '{column}'." for column in expected - actual]
    errors.extend(f"Unexpected column '{column}'." for column in actual - expected)
    return sorted(errors)


def _normalise_location_timeseries(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize both storage formats to stable pandas dtypes."""
    result = data.loc[:, CANONICAL_COLUMNS].copy()
    for column in ("event_sequence", "hcw_id", "patient_id", "door_id", "content_type"):
        values = result[column].replace({"-": pd.NA, "": pd.NA})
        numeric = pd.to_numeric(values, errors="coerce")
        numeric = numeric.where(numeric.isna() | numeric.mod(1).eq(0))
        result[column] = numeric.astype("Int64")

    result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce")
    result["location"] = result["location"].astype("string")
    result["event_type"] = result["event_type"].astype("string")
    return result.sort_values(
        ["hcw_id", "timestamp", "event_sequence"],
        kind="stable",
        ignore_index=True,
    )


def validate_location_timeseries(  # noqa: PLR0912
    data: pd.DataFrame,
    rooms: list[Room],
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
    task_durations: TaskDurationConfig,
) -> LocationDataValidationReport:
    """Collect structural, temporal, and spatial validation findings."""
    errors = _column_errors(data.columns, CANONICAL_COLUMNS)
    warnings: list[str] = []
    if errors:
        return LocationDataValidationReport(tuple(errors), tuple(warnings))
    if data.empty:
        return LocationDataValidationReport(("Location-event input is empty.",))

    sequences = data["event_sequence"]
    if sequences.isna().any():
        errors.append("Event sequences must not be null or invalid.")
    if sequences.dropna().duplicated().any():
        errors.append("Event sequences must be unique.")
    if (sequences.dropna() <= 0).any():
        errors.append("Event sequences must be positive integers.")

    room_index = {(room.building, room.floor, room.name): room for room in rooms}
    allowed_events = set(task_durations.task_duration_mapping)

    for index, row in data.iterrows():
        sequence = row["event_sequence"]
        row_label = int(sequence) if not _is_missing(sequence) else index + 1
        prefix = f"Event {row_label}"

        hcw_id = row["hcw_id"]
        if _is_missing(hcw_id) or int(hcw_id) <= 0:
            errors.append(f"{prefix}: hcw_id must be a positive integer.")

        timestamp_value = row["timestamp"]
        if _is_missing(timestamp_value):
            errors.append(f"{prefix}: timestamp is missing or invalid.")
        else:
            timestamp = pd.Timestamp(timestamp_value)
            if timestamp.tzinfo is not None:
                errors.append(f"{prefix}: timestamp must be timezone-naive.")
            elif timestamp < start_time or timestamp >= end_time:
                errors.append(
                    f"{prefix}: timestamp {timestamp} is outside the simulation window."
                )

        event_type_value = row["event_type"]
        event_type = "" if _is_missing(event_type_value) else str(event_type_value)
        if event_type not in allowed_events:
            errors.append(f"{prefix}: unsupported event_type {event_type!r}.")

        room = _validate_location(row["location"], room_index, prefix, errors)
        patient_id = row["patient_id"]
        door_id = row["door_id"]
        content_type = row["content_type"]

        _validate_conditional_value(
            patient_id,
            "patient_id",
            prefix,
            errors,
            required=event_type == "attend_patient",
        )
        _validate_conditional_value(
            door_id,
            "door_id",
            prefix,
            errors,
            required=event_type == "door_access",
        )
        _validate_conditional_value(
            content_type,
            "content_type",
            prefix,
            errors,
            required=event_type == "occupy_content",
        )

        if (
            room is not None
            and event_type == "door_access"
            and not _is_missing(door_id)
            and int(door_id) not in {door.door_id for door in room.doors}
        ):
            errors.append(
                f"{prefix}: door_id {int(door_id)} is not present in {room.name!r}."
            )

        if (
            room is not None
            and event_type == "occupy_content"
            and not _is_missing(content_type)
        ):
            try:
                expected_content = ContentType(int(content_type))
            except ValueError:
                errors.append(
                    f"{prefix}: content_type {int(content_type)} is not supported."
                )
            else:
                if not any(
                    content.content_type == expected_content
                    for content in room.contents
                ):
                    errors.append(
                        f"{prefix}: content_type {int(content_type)} is not present "
                        f"in {room.name!r}."
                    )

    return LocationDataValidationReport(tuple(errors), tuple(warnings))


def _validate_location(
    value: object,
    room_index: dict[tuple[str, int, str], Room],
    prefix: str,
    errors: list[str],
) -> Room | None:
    """Validate a location string and return its referenced room."""
    if _is_missing(value):
        errors.append(f"{prefix}: location is missing.")
        return None

    parts = str(value).split(":")
    if len(parts) != 3:
        errors.append(f"{prefix}: location must use 'building:floor:room' format.")
        return None

    building, floor_value, room_name = parts
    try:
        floor = int(floor_value)
    except ValueError:
        errors.append(f"{prefix}: location floor {floor_value!r} is not an integer.")
        return None

    room = room_index.get((building, floor, room_name))
    if room is None:
        errors.append(
            f"{prefix}: location {str(value)!r} is not in the building model."
        )
    return room


def _validate_conditional_value(
    value: object,
    column: str,
    prefix: str,
    errors: list[str],
    *,
    required: bool,
) -> None:
    """Validate that an event-specific value is present exactly when required."""
    missing = _is_missing(value)
    if required and missing:
        errors.append(f"{prefix}: {column} is required for this event type.")
    elif not required and not missing:
        errors.append(f"{prefix}: {column} must be null for this event type.")


def _is_missing(value: object) -> bool:
    """Return whether a scalar pandas value represents missing data."""
    return bool(pd.isna(value))
