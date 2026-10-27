"""
Resolve event location keys through TRE-side reference tables.

The functions in this module accept already-loaded tabular inputs. They do not
open databases or persist outputs, keeping database access and sensitive
reference data outside the package boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from amr_hub_abm.data_ingestion.beds import extract_bed_location
from amr_hub_abm.data_ingestion.doors import extract_door_location
from amr_hub_abm.location_resolution import (
    DoorLocationResolution,
    RoomLocationResolution,
    resolve_door_location,
    resolve_room_location,
)

if TYPE_CHECKING:
    from amr_hub_abm.spatial.room import Room


class EventLocationResolutionStatus(StrEnum):
    """Possible outcomes when resolving an event location key."""

    RESOLVED = "resolved"
    REFERENCE_NOT_FOUND = "reference_not_found"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    UNPARSEABLE_LOCATION = "unparseable_location"
    ROOM_CODE_NOT_FOUND = "room_code_not_found"
    ROOM_NOT_IN_MODEL = "room_not_in_model"
    ROOM_HAS_NO_SPATIAL_GEOMETRY = "room_has_no_spatial_geometry"
    ROOM_HAS_NO_DOORS = "room_has_no_doors"
    AMBIGUOUS_DOORS = "ambiguous_doors"
    DOOR_HAS_NO_SPATIAL_GEOMETRY = "door_has_no_spatial_geometry"


@dataclass(frozen=True)
class LocationResolutionReport:
    """
    Resolved and excluded event records from one location-key pathway.

    Parameters
    ----------
    prepared : pandas.DataFrame
        Event records with resolved canonical locations and model coordinates.
    excluded : pandas.DataFrame
        Event records retained for reconciliation, with an explicit failure or
        ambiguity status.

    """

    prepared: pd.DataFrame
    excluded: pd.DataFrame


def resolve_patient_location_events(  # noqa: PLR0913
    events: pd.DataFrame,
    bed_references: pd.DataFrame,
    room_code_mappings: pd.DataFrame,
    rooms: list[Room],
    *,
    building: str,
    floor: int,
    location_id_column: str = "locationID",
    bed_reference_bed_column: str = "bedName",
    mapping_room_code_column: str = "roomCode",
    mapping_room_column: str = "roomName",
    mapping_bed_column: str = "bedName",
) -> LocationResolutionReport:
    """
    Resolve patient-event location keys to representative room coordinates.

    Each event location key is joined to a bed reference record. Its bed
    identifier is parsed and matched to the room-code mapping before resolving
    the resulting canonical room identity against the loaded spatial model.
    The supplied building and floor define the model context for this bed
    reference dataset.

    Parameters
    ----------
    events : pandas.DataFrame
        Patient-event records containing ``location_id_column``.
    bed_references : pandas.DataFrame
        Reference records mapping location keys to bed identifiers.
    room_code_mappings : pandas.DataFrame
        Reference records mapping parsed room and bed names to room codes.
    rooms : list[Room]
        Rooms loaded from the spatial model.
    building : str
        Model building name for the bed-reference dataset.
    floor : int
        Model floor number for the bed-reference dataset.
    location_id_column : str, default="locationID"
        Shared event and bed-reference location-key column.
    bed_reference_bed_column : str, default="bedName"
        Bed-reference column containing the compact bed identifier.
    mapping_room_code_column : str, default="roomCode"
        Room-code mapping column containing canonical room codes.
    mapping_room_column : str, default="roomName"
        Room-code mapping column containing human-readable room names.
    mapping_bed_column : str, default="bedName"
        Room-code mapping column containing human-readable bed names.

    Returns
    -------
    LocationResolutionReport
        Prepared records with room coordinates and excluded records with a
        reconciliation status.

    Raises
    ------
    KeyError
        If a required input column is absent.

    """
    _require_columns(events, {location_id_column}, "events")
    _require_columns(
        bed_references,
        {location_id_column, bed_reference_bed_column},
        "bed references",
    )
    _require_columns(
        room_code_mappings,
        {mapping_room_code_column, mapping_room_column, mapping_bed_column},
        "room-code mappings",
    )
    parser_mappings = room_code_mappings.rename(
        columns={
            mapping_room_code_column: "room_code",
            mapping_room_column: "room_name",
            mapping_bed_column: "ben_name",
        }
    )
    result = _initialise_result(events)

    for index, event in result.iterrows():
        references = bed_references.loc[
            bed_references[location_id_column] == event[location_id_column]
        ]
        if references.empty:
            _set_status(
                result, index, EventLocationResolutionStatus.REFERENCE_NOT_FOUND
            )
            continue
        if len(references) > 1:
            _set_status(
                result, index, EventLocationResolutionStatus.AMBIGUOUS_REFERENCE
            )
            continue

        bed_value = references.iloc[0][bed_reference_bed_column]
        if not isinstance(bed_value, str):
            _set_status(
                result, index, EventLocationResolutionStatus.UNPARSEABLE_LOCATION
            )
            continue
        parsed = extract_bed_location(
            bed_value,
            parser_mappings,
            building=building,
            floor=floor,
        )
        if parsed.room_code is None:
            status = (
                EventLocationResolutionStatus.UNPARSEABLE_LOCATION
                if parsed.room is None
                else EventLocationResolutionStatus.ROOM_CODE_NOT_FOUND
            )
            _set_status(result, index, status)
            continue

        resolution = resolve_room_location(
            parsed.building or building,
            parsed.floor if parsed.floor is not None else floor,
            parsed.room_code,
            rooms,
        )
        _set_room_resolution(result, index, parsed.room_code, resolution)

    return _split_report(result)


def resolve_door_location_events(
    events: pd.DataFrame,
    door_references: pd.DataFrame,
    rooms: list[Room],
    *,
    location_id_column: str = "locationID",
    door_description_column: str = "descriptiveDoorName",
) -> LocationResolutionReport:
    """
    Resolve door-event location keys to unique model-door coordinates.

    Each event location key is joined to its descriptive door name. The name is
    parsed into a canonical room identity, then resolved to a model door only
    when the room has exactly one candidate door. Multi-door rooms are retained
    in the excluded report rather than assigned an arbitrary coordinate.

    Parameters
    ----------
    events : pandas.DataFrame
        Door-event records containing ``location_id_column``.
    door_references : pandas.DataFrame
        Reference records mapping location keys to descriptive door names.
    rooms : list[Room]
        Rooms loaded from the spatial model.
    location_id_column : str, default="locationID"
        Shared event and door-reference location-key column.
    door_description_column : str, default="descriptiveDoorName"
        Door-reference column containing the source description to parse.

    Returns
    -------
    LocationResolutionReport
        Prepared records with door midpoint coordinates and excluded records
        with a reconciliation status.

    Raises
    ------
    KeyError
        If a required input column is absent.

    """
    _require_columns(events, {location_id_column}, "events")
    _require_columns(
        door_references,
        {location_id_column, door_description_column},
        "door references",
    )
    result = _initialise_result(events)

    for index, event in result.iterrows():
        references = door_references.loc[
            door_references[location_id_column] == event[location_id_column]
        ]
        if references.empty:
            _set_status(
                result, index, EventLocationResolutionStatus.REFERENCE_NOT_FOUND
            )
            continue
        if len(references) > 1:
            _set_status(
                result, index, EventLocationResolutionStatus.AMBIGUOUS_REFERENCE
            )
            continue

        description = references.iloc[0][door_description_column]
        if not isinstance(description, str):
            _set_status(
                result, index, EventLocationResolutionStatus.UNPARSEABLE_LOCATION
            )
            continue
        parsed = extract_door_location(description)
        if parsed.building is None or parsed.floor is None or parsed.room_code is None:
            _set_status(
                result, index, EventLocationResolutionStatus.UNPARSEABLE_LOCATION
            )
            continue

        resolution = resolve_door_location(
            parsed.building,
            parsed.floor,
            parsed.room_code,
            rooms,
        )
        _set_door_resolution(result, index, parsed.room_code, resolution)

    return _split_report(result)


def _require_columns(
    frame: pd.DataFrame,
    required_columns: set[str],
    source_name: str,
) -> None:
    """Raise a clear error when an input table lacks a required column."""
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        msg = f"Missing {source_name} columns: {', '.join(sorted(missing_columns))}"
        raise KeyError(msg)


def _initialise_result(events: pd.DataFrame) -> pd.DataFrame:
    """Create an event copy with standardised spatial-resolution fields."""
    result = events.copy()
    result["model_building"] = pd.Series(pd.NA, index=result.index, dtype="string")
    result["model_floor"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["model_room_code"] = pd.Series(pd.NA, index=result.index, dtype="string")
    result["model_door_id"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["candidate_door_count"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["x"] = pd.Series(pd.NA, index=result.index, dtype="Float64")
    result["y"] = pd.Series(pd.NA, index=result.index, dtype="Float64")
    result["location"] = pd.Series(pd.NA, index=result.index, dtype="string")
    result["resolution_status"] = pd.Series(pd.NA, index=result.index, dtype="string")
    return result


def _set_status(
    result: pd.DataFrame,
    index: object,
    status: EventLocationResolutionStatus,
) -> None:
    """Set one reconciliation status without implying a model location."""
    result.loc[index, "resolution_status"] = status


def _set_room_resolution(
    result: pd.DataFrame,
    index: object,
    room_code: str,
    resolution: RoomLocationResolution,
) -> None:
    """Write a room-resolution result to one event record."""
    room = resolution.room
    if room is not None:
        result.loc[index, "model_building"] = room.building
        result.loc[index, "model_floor"] = room.floor
    result.loc[index, "model_room_code"] = room_code
    result.loc[index, "resolution_status"] = resolution.status.value
    if resolution.location is not None:
        result.loc[index, "x"] = resolution.location.x
        result.loc[index, "y"] = resolution.location.y
        result.loc[index, "location"] = (
            f"{resolution.location.building}:{resolution.location.floor}:{room_code}"
        )


def _set_door_resolution(
    result: pd.DataFrame,
    index: object,
    room_code: str,
    resolution: DoorLocationResolution,
) -> None:
    """Write a door-resolution result to one event record."""
    room = resolution.room
    if room is not None:
        result.loc[index, "model_building"] = room.building
        result.loc[index, "model_floor"] = room.floor
    result.loc[index, "model_room_code"] = room_code
    result.loc[index, "candidate_door_count"] = resolution.candidate_door_count
    result.loc[index, "resolution_status"] = resolution.status.value
    if resolution.door is not None:
        result.loc[index, "model_door_id"] = resolution.door.door_id
    if resolution.location is not None:
        result.loc[index, "x"] = resolution.location.x
        result.loc[index, "y"] = resolution.location.y
        result.loc[index, "location"] = (
            f"{resolution.location.building}:{resolution.location.floor}:{room_code}"
        )


def _split_report(result: pd.DataFrame) -> LocationResolutionReport:
    """Split records into prepared and excluded outputs by resolution status."""
    resolved = result["resolution_status"] == EventLocationResolutionStatus.RESOLVED
    return LocationResolutionReport(
        prepared=result.loc[resolved].copy(),
        excluded=result.loc[~resolved].copy(),
    )
