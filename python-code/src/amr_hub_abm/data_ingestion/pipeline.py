"""Prepare roster-filtered location events for direct simulation input."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import pandas as pd

from amr_hub_abm.data_ingestion.prepared_events import (
    SIMULATOR_EVENT_COLUMNS,
    LocationEventPreparationReport,
    prepare_location_events,
)
from amr_hub_abm.data_ingestion.reference_locations import EventLocationResolutionStatus
from amr_hub_abm.exceptions import InvalidDefinitionError, LocationDataValidationError
from amr_hub_abm.location_data import (
    DUCKDB_METADATA_TABLE,
    LOCATION_SCHEMA_COMPONENT,
    LOCATION_SCHEMA_VERSION,
    validate_location_timeseries,
)
from amr_hub_abm.read_space_input import SpaceInputReader

if TYPE_CHECKING:
    from numpy.random import Generator

    from amr_hub_abm.config import SimulationConfig

logger = logging.getLogger(__name__)

AUDIT_TABLE_NAME = "location_reconciliation_audit"


class RosterFilterStatus(StrEnum):
    """Reasons a resolved event is excluded before simulation."""

    OUTSIDE_SIMULATION_WINDOW = "outside_simulation_window"
    HCW_NOT_ROSTERED = "hcw_not_rostered"
    OUTSIDE_ROSTERED_SHIFT = "outside_rostered_shift"


@dataclass(frozen=True)
class RosterColumns:
    """Column names used by the approved roster extract."""

    hcw_id: str = "hcw_id"
    shift_start: str = "shift_start"
    shift_end: str = "shift_end"


DEFAULT_ROSTER_COLUMNS = RosterColumns()


def prepare_simulation_location_data(  # noqa: PLR0913
    events: pd.DataFrame,
    bed_references: pd.DataFrame,
    room_code_mappings: pd.DataFrame,
    door_references: pd.DataFrame,
    roster: pd.DataFrame,
    config: SimulationConfig,
    *,
    patient_building: str,
    patient_floor: int,
    rng_generator: Generator,
    roster_columns: RosterColumns = DEFAULT_ROSTER_COLUMNS,
) -> LocationEventPreparationReport:
    """
    Prepare supported events using the configured model and roster coverage.

    The configured simulation window is authoritative. Roster records only
    determine whether a healthcare worker is eligible to contribute an event at
    a particular time. Events without valid location resolution or roster
    coverage remain in the audit and are logged as warnings rather than being
    silently included in simulator input.

    Parameters
    ----------
    events : pandas.DataFrame
        Source interaction events.
    bed_references : pandas.DataFrame
        Source location-key to bed-reference records.
    room_code_mappings : pandas.DataFrame
        Source bed-reference to canonical room-code records.
    door_references : pandas.DataFrame
        Source location-key to door-description records.
    roster : pandas.DataFrame
        Healthcare-worker roster intervals.
    config : amr_hub_abm.config.SimulationConfig
        Simulation configuration defining the spatial model and time window.
    patient_building : str
        Model building containing patient-bed references.
    patient_floor : int
        Model floor containing patient-bed references.
    rng_generator : numpy.random.Generator
        Random generator used while loading the spatial model.
    roster_columns : RosterColumns, optional
        Column names in ``roster``.

    Returns
    -------
    LocationEventPreparationReport
        Simulator-ready resolved rows and a complete source-event audit.

    Raises
    ------
    InvalidDefinitionError
        If the configured time window, source event identifiers, or roster
        intervals are malformed.
    LocationDataValidationError
        If no events remain for simulation or resolved events fail the
        simulator's location-event contract.

    """
    start_time, end_time = _simulation_window(config)
    _validate_event_values(events)
    roster_intervals = _normalise_roster(roster, roster_columns)
    reader = SpaceInputReader(_buildings_path(config), rng_generator)

    report = prepare_location_events(
        events,
        bed_references,
        room_code_mappings,
        door_references,
        reader.rooms,
        patient_building=patient_building,
        patient_floor=patient_floor,
    )
    filtered_report = _filter_report_to_roster(
        report,
        roster_intervals,
        start_time=start_time,
        end_time=end_time,
    )
    _log_audit_summary(filtered_report.audit)

    if filtered_report.location_timeseries.empty:
        raise LocationDataValidationError(
            (
                "No resolved location events remain after reconciliation and roster "
                "filtering.",
            )
        )

    validation_report = validate_location_timeseries(
        filtered_report.location_timeseries,
        reader.rooms,
        start_time,
        end_time,
        config.task_durations,
    )
    for warning in validation_report.warnings:
        logger.warning("Location data validation warning: %s", warning)
    validation_report.raise_for_errors()
    return filtered_report


def write_location_event_database(
    report: LocationEventPreparationReport,
    output_path: Path,
) -> None:
    """Write prepared simulator events and their audit to a new DuckDB database."""
    if report.location_timeseries.empty:
        msg = "Cannot write a location-event database with no simulator events."
        raise LocationDataValidationError((msg,))
    if output_path.exists():
        msg = f"Location-event output already exists: {output_path}"
        raise FileExistsError(msg)
    if not output_path.parent.exists():
        msg = f"Location-event output directory does not exist: {output_path.parent}"
        raise FileNotFoundError(msg)

    with duckdb.connect(str(output_path)) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
            connection.execute(
                f"CREATE TABLE {DUCKDB_METADATA_TABLE} "
                "(component VARCHAR PRIMARY KEY, schema_version INTEGER NOT NULL)"
            )
            connection.execute(
                f"INSERT INTO {DUCKDB_METADATA_TABLE} VALUES (?, ?)",  # noqa: S608
                [LOCATION_SCHEMA_COMPONENT, LOCATION_SCHEMA_VERSION],
            )
            connection.execute(
                """
                CREATE TABLE location_timeseries (
                    event_sequence BIGINT,
                    hcw_id INTEGER,
                    timestamp TIMESTAMP,
                    location VARCHAR,
                    event_type VARCHAR,
                    patient_id INTEGER,
                    door_id INTEGER,
                    content_type INTEGER
                )
                """
            )
            connection.register("prepared_location_events", report.location_timeseries)
            connection.execute(
                """
                INSERT INTO location_timeseries
                SELECT
                    CAST(event_sequence AS BIGINT),
                    CAST(hcw_id AS INTEGER),
                    CAST(timestamp AS TIMESTAMP),
                    CAST(location AS VARCHAR),
                    CAST(event_type AS VARCHAR),
                    CAST(patient_id AS INTEGER),
                    CAST(door_id AS INTEGER),
                    CAST(content_type AS INTEGER)
                FROM prepared_location_events
                ORDER BY timestamp, event_sequence, hcw_id
                """
            )
            connection.unregister("prepared_location_events")
            connection.register("location_event_audit", report.audit)
            connection.execute(
                f"CREATE TABLE {AUDIT_TABLE_NAME} AS "  # noqa: S608
                "SELECT * FROM location_event_audit"
            )
            connection.unregister("location_event_audit")
            connection.execute("COMMIT")
        except duckdb.Error:
            connection.execute("ROLLBACK")
            raise


def build_simulation_location_database(  # noqa: PLR0913
    events: pd.DataFrame,
    bed_references: pd.DataFrame,
    room_code_mappings: pd.DataFrame,
    door_references: pd.DataFrame,
    roster: pd.DataFrame,
    config: SimulationConfig,
    output_path: Path,
    *,
    patient_building: str,
    patient_floor: int,
    rng_generator: Generator,
    roster_columns: RosterColumns = DEFAULT_ROSTER_COLUMNS,
) -> LocationEventPreparationReport:
    """Prepare and persist a simulator-ready location-event database."""
    report = prepare_simulation_location_data(
        events,
        bed_references,
        room_code_mappings,
        door_references,
        roster,
        config,
        patient_building=patient_building,
        patient_floor=patient_floor,
        rng_generator=rng_generator,
        roster_columns=roster_columns,
    )
    write_location_event_database(report, output_path)
    return report


def _simulation_window(config: SimulationConfig) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Read and validate the authoritative simulation interval."""
    try:
        start_time = pd.Timestamp(config.config_data["start_time"])
        end_time = pd.Timestamp(config.config_data["end_time"])
    except (KeyError, TypeError, ValueError) as exc:
        msg = "Simulation configuration must define valid start_time and end_time."
        raise InvalidDefinitionError(msg) from exc
    if pd.isna(start_time) or pd.isna(end_time) or start_time >= end_time:
        msg = "Simulation start_time must be earlier than end_time."
        raise InvalidDefinitionError(msg)
    if start_time.tz is not None or end_time.tz is not None:
        msg = "Simulation start_time and end_time must be timezone-naive."
        raise InvalidDefinitionError(msg)
    return start_time, end_time


def _buildings_path(config: SimulationConfig) -> Path:
    """Read the configured spatial-model path."""
    buildings_path = config.config_data.get("buildings_path")
    if not isinstance(buildings_path, (str, Path)):
        msg = "Simulation configuration must define a buildings_path."
        raise InvalidDefinitionError(msg)
    return Path(buildings_path)


def _validate_event_values(events: pd.DataFrame) -> None:
    """Reject malformed event identifiers and timestamps before reconciliation."""
    required_columns = {"hcw_id", "timestamp"}
    missing_columns = required_columns.difference(events.columns)
    if missing_columns:
        msg = f"Missing event columns: {', '.join(sorted(missing_columns))}"
        raise KeyError(msg)

    hcw_ids = pd.to_numeric(events["hcw_id"], errors="coerce")
    invalid_hcw_ids = hcw_ids.isna() | hcw_ids.mod(1).ne(0) | hcw_ids.le(0)
    if invalid_hcw_ids.any():
        msg = "Event hcw_id values must be positive integers."
        raise InvalidDefinitionError(msg)

    timestamps = pd.to_datetime(events["timestamp"], errors="coerce")
    if timestamps.isna().any():
        msg = "Event timestamps must be valid."
        raise InvalidDefinitionError(msg)
    if getattr(timestamps.dt, "tz", None) is not None:
        msg = "Event timestamps must be timezone-naive."
        raise InvalidDefinitionError(msg)


def _normalise_roster(
    roster: pd.DataFrame,
    columns: RosterColumns,
) -> pd.DataFrame:
    """Validate roster shifts and return normalized matching columns."""
    required_columns = {columns.hcw_id, columns.shift_start, columns.shift_end}
    missing_columns = required_columns.difference(roster.columns)
    if missing_columns:
        msg = f"Missing roster columns: {', '.join(sorted(missing_columns))}"
        raise KeyError(msg)

    result = roster.loc[
        :, [columns.hcw_id, columns.shift_start, columns.shift_end]
    ].copy()
    result.columns = ["hcw_id", "shift_start", "shift_end"]
    result["hcw_id"] = pd.to_numeric(result["hcw_id"], errors="coerce")
    result["shift_start"] = pd.to_datetime(result["shift_start"], errors="coerce")
    result["shift_end"] = pd.to_datetime(result["shift_end"], errors="coerce")
    invalid_hcw_ids = (
        result["hcw_id"].isna() | result["hcw_id"].mod(1).ne(0) | result["hcw_id"].le(0)
    )
    invalid_intervals = (
        result["shift_start"].isna()
        | result["shift_end"].isna()
        | result["shift_start"].ge(result["shift_end"])
    )
    if invalid_hcw_ids.any() or invalid_intervals.any():
        msg = "Roster rows require a positive hcw_id and increasing shift interval."
        raise InvalidDefinitionError(msg)
    if getattr(result["shift_start"].dt, "tz", None) is not None:
        msg = "Roster shift timestamps must be timezone-naive."
        raise InvalidDefinitionError(msg)
    result["hcw_id"] = result["hcw_id"].astype("Int64")
    return result


def _filter_report_to_roster(
    report: LocationEventPreparationReport,
    roster: pd.DataFrame,
    *,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
) -> LocationEventPreparationReport:
    """Replace resolved statuses when events lack temporal roster coverage."""
    audit = report.audit.copy()
    resolved = audit["resolution_status"] == EventLocationResolutionStatus.RESOLVED
    for index, event in audit.loc[resolved].iterrows():
        timestamp = pd.Timestamp(event["timestamp"])
        if timestamp < start_time or timestamp >= end_time:
            audit.loc[index, "resolution_status"] = (
                RosterFilterStatus.OUTSIDE_SIMULATION_WINDOW
            )
            continue

        shifts = roster.loc[roster["hcw_id"] == int(event["hcw_id"])]
        if shifts.empty:
            audit.loc[index, "resolution_status"] = RosterFilterStatus.HCW_NOT_ROSTERED
            continue
        active_shift = (shifts["shift_start"] <= timestamp) & (
            timestamp < shifts["shift_end"]
        )
        if not active_shift.any():
            audit.loc[index, "resolution_status"] = (
                RosterFilterStatus.OUTSIDE_ROSTERED_SHIFT
            )

    retained_sequences = set(
        audit.loc[
            audit["resolution_status"] == EventLocationResolutionStatus.RESOLVED,
            "event_sequence",
        ]
    )
    location_timeseries = report.location_timeseries.loc[
        report.location_timeseries["event_sequence"].isin(retained_sequences)
    ].reindex(columns=SIMULATOR_EVENT_COLUMNS)
    return LocationEventPreparationReport(
        location_timeseries=location_timeseries,
        audit=audit,
    )


def _log_audit_summary(audit: pd.DataFrame) -> None:
    """Log warning counts for every event excluded from simulation input."""
    excluded = audit.loc[
        audit["resolution_status"] != EventLocationResolutionStatus.RESOLVED
    ]
    for status, count in excluded["resolution_status"].value_counts(sort=False).items():
        logger.warning("Excluded %d source events with status %s", count, status)
