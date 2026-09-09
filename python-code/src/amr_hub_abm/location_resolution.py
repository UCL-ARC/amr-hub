"""
Resolve canonical room identities to deterministic model coordinates.

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
