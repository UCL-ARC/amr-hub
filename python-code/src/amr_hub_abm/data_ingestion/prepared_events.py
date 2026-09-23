"""Prepare resolved source events for the simulator location-event contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from amr_hub_abm.data_ingestion.reference_locations import (
    EventLocationResolutionStatus,
    resolve_door_location_events,
    resolve_patient_location_events,
)
from amr_hub_abm.exceptions import InvalidDefinitionError

if TYPE_CHECKING:
    from amr_hub_abm.spatial.room import Room


SIMULATOR_EVENT_COLUMNS = (
    "event_sequence",
    "hcw_id",
    "timestamp",
    "location",
    "event_type",
    "patient_id",
    "door_id",
    "content_type",
)


class EventPreparationStatus(StrEnum):
    """Preparation outcomes that are not location-resolution outcomes."""

    UNSUPPORTED_INTERACTION_TYPE = "unsupported_interaction_type"


@dataclass(frozen=True)
class LocationEventPreparationReport:
    """
    Simulator-ready location events and their complete mapping audit trail.

    Parameters
    ----------
    location_timeseries : pandas.DataFrame
        Successfully resolved events using the fixed input columns proposed by
        the validated DuckDB location-event reader.
    audit : pandas.DataFrame
        One row for every source event. It records the source event identifier,
        assigned event sequence, resolution status, and mapping details.

    """

    location_timeseries: pd.DataFrame
    audit: pd.DataFrame


def prepare_location_events(  # noqa: PLR0913
    events: pd.DataFrame,
    bed_references: pd.DataFrame,
    room_code_mappings: pd.DataFrame,
    door_references: pd.DataFrame,
    rooms: list[Room],
    *,
    patient_building: str,
    patient_floor: int,
    source_event_id_column: str = "eventID",
    location_id_column: str = "locationID",
) -> LocationEventPreparationReport:
    """
    Prepare supported source events for validated simulator input.

    Patient-attendance events resolve through bed references; door-access events
    resolve through door references. Other interaction types remain in the
    audit with an explicit status. Resolved events use the fixed event columns
    required by the DuckDB location-event reader, while the audit retains the
    source identifier and model-resolution details for every input event.

    Parameters
    ----------
    events : pandas.DataFrame
        Source events using the simulator field names, together with a source
        event identifier and location reference key.
    bed_references : pandas.DataFrame
        TRE-side location-key to bed-reference records.
    room_code_mappings : pandas.DataFrame
        TRE-side bed-reference to canonical room-code records.
    door_references : pandas.DataFrame
        TRE-side location-key to descriptive door-reference records.
    rooms : list[Room]
        Rooms loaded from the spatial model.
    patient_building : str
        Model building containing the patient bed references.
    patient_floor : int
        Model floor containing the patient bed references.
    source_event_id_column : str, default="eventID"
        Unique source event identifier retained in the audit output.
    location_id_column : str, default="locationID"
        Event and reference-table location-key column.

    Returns
    -------
    LocationEventPreparationReport
        Resolved simulator events and a complete per-source-event audit.

    Raises
    ------
    KeyError
        If source events lack required columns.
    InvalidDefinitionError
        If the source event identifier is missing or duplicated.

    """
    required_columns = {
        source_event_id_column,
        location_id_column,
        "hcw_id",
        "timestamp",
        "event_type",
        "patient_id",
        "door_id",
        "content_type",
    }
    missing_columns = required_columns.difference(events.columns)
    if missing_columns:
        msg = f"Missing event columns: {', '.join(sorted(missing_columns))}"
        raise KeyError(msg)
    if events[source_event_id_column].isna().any():
        msg = f"Source event identifier '{source_event_id_column}' must not be missing"
        raise InvalidDefinitionError(msg)
    if events[source_event_id_column].duplicated().any():
        msg = f"Source event identifier '{source_event_id_column}' must be unique"
        raise InvalidDefinitionError(msg)

    source_events = events.copy()
    source_events["_source_event_id"] = source_events[source_event_id_column]
    source_events["_source_order"] = range(1, len(source_events) + 1)
    source_events["event_sequence"] = source_events["_source_order"]

    patient_events = source_events.loc[source_events["event_type"] == "attend_patient"]
    door_events = source_events.loc[source_events["event_type"] == "door_access"]
    unsupported_events = source_events.loc[
        ~source_events["event_type"].isin({"attend_patient", "door_access"})
    ].copy()

    resolved_reports = []
    if not patient_events.empty:
        patient_report = resolve_patient_location_events(
            patient_events,
            bed_references,
            room_code_mappings,
            rooms,
            building=patient_building,
            floor=patient_floor,
            location_id_column=location_id_column,
        )
        resolved_reports.extend([patient_report.prepared, patient_report.excluded])
    if not door_events.empty:
        door_report = resolve_door_location_events(
            door_events,
            door_references,
            rooms,
            location_id_column=location_id_column,
        )
        resolved_reports.extend([door_report.prepared, door_report.excluded])

    if not unsupported_events.empty:
        unsupported_events["resolution_status"] = (
            EventPreparationStatus.UNSUPPORTED_INTERACTION_TYPE
        )
        resolved_reports.append(unsupported_events)

    if resolved_reports:
        audit = pd.concat(resolved_reports, ignore_index=True)
        audit = audit.sort_values("_source_order", kind="stable", ignore_index=True)
    else:
        audit = source_events.copy()
        audit["resolution_status"] = pd.Series(dtype="string")
    audit = audit.rename(columns={"_source_event_id": "source_event_id"})

    resolved = audit["resolution_status"] == EventLocationResolutionStatus.RESOLVED
    location_timeseries = audit.loc[resolved].reindex(columns=SIMULATOR_EVENT_COLUMNS)
    door_events_resolved = location_timeseries["event_type"] == "door_access"
    if door_events_resolved.any():
        location_timeseries.loc[door_events_resolved, "door_id"] = audit.loc[
            resolved & (audit["event_type"] == "door_access"), "model_door_id"
        ].to_numpy()

    audit = audit.drop(columns=["_source_order"])
    return LocationEventPreparationReport(
        location_timeseries=location_timeseries,
        audit=audit,
    )
