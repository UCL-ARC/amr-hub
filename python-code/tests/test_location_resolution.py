"""Tests for deterministic model room-location resolution."""

import numpy as np
import pytest

from amr_hub_abm.location_resolution import (
    DoorResolutionStatus,
    RoomResolutionStatus,
    resolve_door_location,
    resolve_room_location,
)
from amr_hub_abm.spatial.door import Door
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.spatial.wall import Wall


def make_room(
    name: str,
    building: str,
    floor: int,
    coordinates: list[tuple[float, float]],
    doors: list[Door] | None = None,
) -> Room:
    """Create a spatial room from a closed sequence of synthetic coordinates."""
    walls = [
        Wall(start=start, end=end)
        for start, end in zip(
            coordinates,
            [*coordinates[1:], coordinates[0]],
            strict=True,
        )
    ]
    return Room(
        room_id=1,
        name=name,
        building=building,
        floor=floor,
        contents=[],
        doors=[] if doors is None else doors,
        walls=walls,
        rng_generator=np.random.default_rng(),
    )


def test_resolve_room_location_returns_interior_centroid() -> None:
    """A convex model room resolves to its polygon centroid."""
    room = make_room(
        name="TEST-001",
        building="Test Building",
        floor=1,
        coordinates=[(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)],
    )

    result = resolve_room_location("Test Building", 1, "TEST-001", [room])

    assert result.status is RoomResolutionStatus.RESOLVED
    assert result.room is room
    assert result.location is not None
    assert result.location.x == pytest.approx(2.0)
    assert result.location.y == pytest.approx(1.0)


def test_resolve_room_location_uses_interior_fallback_for_concave_room() -> None:
    """An exterior centroid is replaced with a valid interior point."""
    room = make_room(
        name="TEST-002",
        building="Test Building",
        floor=1,
        coordinates=[
            (0.0, 0.0),
            (4.0, 0.0),
            (4.0, 1.0),
            (1.0, 1.0),
            (1.0, 4.0),
            (0.0, 4.0),
        ],
    )

    result = resolve_room_location("Test Building", 1, "TEST-002", [room])

    assert not room.region.contains(room.region.centroid)
    assert result.status is RoomResolutionStatus.RESOLVED
    assert result.location is not None
    assert room.contains_point((result.location.x, result.location.y))


def test_resolve_room_location_reports_missing_model_room() -> None:
    """An unmatched canonical room code returns an explicit missing status."""
    result = resolve_room_location("Test Building", 1, "TEST-003", [])

    assert result.status is RoomResolutionStatus.ROOM_NOT_IN_MODEL
    assert result.room is None
    assert result.location is None


def test_resolve_room_location_reports_room_without_spatial_geometry() -> None:
    """A topological room cannot supply a representative coordinate."""
    room = Room(
        room_id=1,
        name="TEST-004",
        building="Test Building",
        floor=1,
        contents=[],
        doors=[],
        area=10.0,
        rng_generator=np.random.default_rng(),
    )

    result = resolve_room_location("Test Building", 1, "TEST-004", [room])

    assert result.status is RoomResolutionStatus.ROOM_HAS_NO_SPATIAL_GEOMETRY
    assert result.room is room
    assert result.location is None


def test_resolve_door_location_returns_unique_door_midpoint() -> None:
    """A room with one door resolves to the centre of its door segment."""
    door = Door(
        is_open=False,
        access_control=(False, False),
        start=(1.0, 0.0),
        end=(3.0, 0.0),
        connecting_rooms=(1, 2),
        door_id=1,
    )
    room = make_room(
        name="TEST-005",
        building="Test Building",
        floor=1,
        coordinates=[(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)],
        doors=[door],
    )

    result = resolve_door_location("Test Building", 1, "TEST-005", [room])

    assert result.status is DoorResolutionStatus.RESOLVED
    assert result.room is room
    assert result.door is door
    assert result.candidate_door_count == 1
    assert result.location is not None
    assert result.location.x == pytest.approx(2.0)
    assert result.location.y == pytest.approx(0.0)


def test_resolve_door_location_reports_room_without_doors() -> None:
    """A room-level match cannot resolve a door when the room has none."""
    room = make_room(
        name="TEST-006",
        building="Test Building",
        floor=1,
        coordinates=[(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)],
    )

    result = resolve_door_location("Test Building", 1, "TEST-006", [room])

    assert result.status is DoorResolutionStatus.ROOM_HAS_NO_DOORS
    assert result.door is None
    assert result.location is None
    assert result.candidate_door_count == 0


def test_resolve_door_location_reports_ambiguous_model_doors() -> None:
    """A room with multiple doors is retained as an explicit ambiguity."""
    doors = [
        Door(
            is_open=False,
            access_control=(False, False),
            start=(1.0, 0.0),
            end=(2.0, 0.0),
            connecting_rooms=(1, 2),
            door_id=1,
        ),
        Door(
            is_open=False,
            access_control=(False, False),
            start=(4.0, 0.5),
            end=(4.0, 1.5),
            connecting_rooms=(1, 3),
            door_id=2,
        ),
    ]
    room = make_room(
        name="TEST-007",
        building="Test Building",
        floor=1,
        coordinates=[(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)],
        doors=doors,
    )

    result = resolve_door_location("Test Building", 1, "TEST-007", [room])

    assert result.status is DoorResolutionStatus.AMBIGUOUS_DOORS
    assert result.door is None
    assert result.location is None
    assert result.candidate_door_count == 2


def test_resolve_door_location_propagates_missing_model_room() -> None:
    """A missing room remains unresolved before door selection."""
    result = resolve_door_location("Test Building", 1, "TEST-008", [])

    assert result.status is DoorResolutionStatus.ROOM_NOT_IN_MODEL
    assert result.room is None
    assert result.door is None
    assert result.location is None
