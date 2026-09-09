"""
Resolve canonical room and door identities to deterministic model coordinates.

This module is deliberately independent of source databases and reference
tables. It resolves an already-normalised building, floor, and room code
against loaded model rooms. The resulting coordinate is a temporary modelling
assumption, rather than an observed position: use the room polygon centroid
when it is interior, otherwise an interior representative point.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from amr_hub_abm.spatial.location import Location

if TYPE_CHECKING:
    from amr_hub_abm.spatial.door import Door
    from amr_hub_abm.spatial.room import Room


class RoomResolutionStatus(StrEnum):
    """Possible outcomes when resolving a canonical room identity."""

    RESOLVED = "resolved"
    ROOM_NOT_IN_MODEL = "room_not_in_model"
    ROOM_HAS_NO_SPATIAL_GEOMETRY = "room_has_no_spatial_geometry"


@dataclass(frozen=True)
class RoomLocationResolution:
    """
    Result of resolving one canonical room identity in a spatial model.

    Parameters
    ----------
    status : RoomResolutionStatus
        Outcome of the room lookup and spatial placement.
    room : Room | None
        Matched model room, when one exists.
    location : Location | None
        Deterministic representative coordinate, when spatial resolution
        succeeds.

    """

    status: RoomResolutionStatus
    room: Room | None
    location: Location | None


class DoorResolutionStatus(StrEnum):
    """Possible outcomes when resolving a canonical room identity to a door."""

    RESOLVED = "resolved"
    ROOM_NOT_IN_MODEL = "room_not_in_model"
    ROOM_HAS_NO_SPATIAL_GEOMETRY = "room_has_no_spatial_geometry"
    ROOM_HAS_NO_DOORS = "room_has_no_doors"
    AMBIGUOUS_DOORS = "ambiguous_doors"
    DOOR_HAS_NO_SPATIAL_GEOMETRY = "door_has_no_spatial_geometry"


@dataclass(frozen=True)
class DoorLocationResolution:
    """
    Result of resolving one canonical room identity to a model door.

    Parameters
    ----------
    status : DoorResolutionStatus
        Outcome of the room lookup and door selection.
    room : Room | None
        Matched model room, when one exists.
    door : Door | None
        Selected model door when the room has exactly one spatial door.
    location : Location | None
        Midpoint of the selected door segment, when resolution succeeds.
    candidate_door_count : int
        Number of model doors in the matched room. This allows callers to
        report unresolved multi-door records without re-inspecting geometry.

    """

    status: DoorResolutionStatus
    room: Room | None
    door: Door | None
    location: Location | None
    candidate_door_count: int


def resolve_room_location(
    building: str,
    floor: int,
    room_code: str,
    rooms: list[Room],
) -> RoomLocationResolution:
    """
    Resolve a canonical room identity to a deterministic model coordinate.

    The function has no source-data or persistence dependencies. It is intended
    to be called after location ingestion has produced canonical identifiers.
    A room centroid is used as the temporary representative location. Concave
    polygons can have an exterior centroid, so the function falls back to an
    interior representative point to ensure that successful resolutions are
    valid positions in the model.

    Parameters
    ----------
    building : str
        Building name matching ``Room.building``.
    floor : int
        Floor number matching ``Room.floor``.
    room_code : str
        Canonical room code matching ``Room.name``.
    rooms : list[Room]
        Rooms loaded from the spatial model.

    Returns
    -------
    RoomLocationResolution
        Resolution result. A missing model room or a topological room without
        spatial geometry returns no coordinate.

    """
    room = next(
        (
            candidate
            for candidate in rooms
            if candidate.building == building
            and candidate.floor == floor
            and candidate.name == room_code
        ),
        None,
    )
    if room is None:
        return RoomLocationResolution(
            status=RoomResolutionStatus.ROOM_NOT_IN_MODEL,
            room=None,
            location=None,
        )

    if room.region.is_empty:
        return RoomLocationResolution(
            status=RoomResolutionStatus.ROOM_HAS_NO_SPATIAL_GEOMETRY,
            room=room,
            location=None,
        )

    point = room.region.centroid
    if not room.region.contains(point):
        point = room.region.representative_point()

    return RoomLocationResolution(
        status=RoomResolutionStatus.RESOLVED,
        room=room,
        location=Location(
            building=room.building,
            floor=room.floor,
            x=point.x,
            y=point.y,
        ),
    )


def resolve_door_location(
    building: str,
    floor: int,
    room_code: str,
    rooms: list[Room],
) -> DoorLocationResolution:
    """
    Resolve a canonical room identity to the midpoint of its unique door.

    The source location description identifies a room rather than a model door.
    To avoid introducing an unsupported arbitrary selection rule, this function
    resolves only rooms with exactly one door. Rooms with no doors or multiple
    doors return explicit outcomes for later reconciliation. As with room
    resolution, this function has no source-data or persistence dependencies.

    Parameters
    ----------
    building : str
        Building name matching ``Room.building``.
    floor : int
        Floor number matching ``Room.floor``.
    room_code : str
        Canonical room code matching ``Room.name``.
    rooms : list[Room]
        Rooms loaded from the spatial model.

    Returns
    -------
    DoorLocationResolution
        Resolution result with the unique door midpoint when exactly one spatial
        model door belongs to the resolved room.

    """
    room_resolution = resolve_room_location(building, floor, room_code, rooms)
    if room_resolution.status is RoomResolutionStatus.ROOM_NOT_IN_MODEL:
        return DoorLocationResolution(
            status=DoorResolutionStatus.ROOM_NOT_IN_MODEL,
            room=None,
            door=None,
            location=None,
            candidate_door_count=0,
        )
    if room_resolution.status is RoomResolutionStatus.ROOM_HAS_NO_SPATIAL_GEOMETRY:
        return DoorLocationResolution(
            status=DoorResolutionStatus.ROOM_HAS_NO_SPATIAL_GEOMETRY,
            room=room_resolution.room,
            door=None,
            location=None,
            candidate_door_count=0,
        )

    room = room_resolution.room
    if room is None:
        msg = "A resolved room location must contain a room."
        raise RuntimeError(msg)

    candidate_door_count = len(room.doors)
    if candidate_door_count == 0:
        return DoorLocationResolution(
            status=DoorResolutionStatus.ROOM_HAS_NO_DOORS,
            room=room,
            door=None,
            location=None,
            candidate_door_count=0,
        )
    if candidate_door_count > 1:
        return DoorLocationResolution(
            status=DoorResolutionStatus.AMBIGUOUS_DOORS,
            room=room,
            door=None,
            location=None,
            candidate_door_count=candidate_door_count,
        )

    door = room.doors[0]
    if door.start is None or door.end is None:
        return DoorLocationResolution(
            status=DoorResolutionStatus.DOOR_HAS_NO_SPATIAL_GEOMETRY,
            room=room,
            door=door,
            location=None,
            candidate_door_count=1,
        )

    midpoint = door.line.interpolate(0.5, normalized=True)
    return DoorLocationResolution(
        status=DoorResolutionStatus.RESOLVED,
        room=room,
        door=door,
        location=Location(
            building=room.building,
            floor=room.floor,
            x=midpoint.x,
            y=midpoint.y,
        ),
        candidate_door_count=1,
    )
