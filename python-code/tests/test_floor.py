"""Tests for the Floor class in amr_hub_abm.space.floor module."""

import numpy as np
import pytest

from amr_hub_abm.exceptions import InvalidRoomError
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall


def _make_room(
    room_id: int, name: str, area: float = 10.0, doors: list[Door] | None = None
) -> Room:
    if doors is None:
        doors = []
    return Room(
        room_id=room_id,
        name=name,
        building="B1",
        floor=1,
        contents=[],
        doors=doors,
        area=area,
    )


def _make_door(
    a: int,
    b: int,
    start: tuple[float, float] = (0.0, 0.0),
    end: tuple[float, float] = (1.0, 0.0),
) -> Door:
    return Door(
        open=True,
        connecting_rooms=(a, b),
        access_control=(True, True),
        start=start,
        end=end,
        door_id=0,
    )


def test_room_ids_and_names_sorted() -> None:
    """Test that room IDs and names are returned in sorted order."""
    r2 = _make_room(2, "B")
    r1 = _make_room(1, "A")
    r3 = _make_room(3, "C")

    floor = Floor(floor_number=1, rooms=[r2, r1, r3])

    assert floor.room_ids == [1, 2, 3]
    assert floor.room_names == ["A", "B", "C"]


def test_duplicate_room_ids_raises() -> None:
    """Test that duplicate room IDs raise an InvalidRoomError."""
    r1 = _make_room(1, "A")
    r1b = _make_room(1, "A2")

    with pytest.raises(InvalidRoomError) as exc_info:
        Floor(floor_number=1, rooms=[r1, r1b])
    assert "Duplicate room IDs" in str(exc_info.value)


def test_edge_set_and_adjacency_matrix() -> None:
    """Test that edge set and adjacency matrix are computed correctly."""
    # Create doors connecting 1-2 and 2-3
    d12 = _make_door(1, 2, start=(0.0, 0.0), end=(1.0, 0.0))
    d23 = _make_door(2, 3, start=(1.0, 0.0), end=(2.0, 0.0))

    r1 = _make_room(1, "R1", doors=[d12])
    r2 = _make_room(2, "R2", doors=[d12, d23])
    r3 = _make_room(3, "R3", doors=[d23])

    floor = Floor(floor_number=1, rooms=[r1, r2, r3])

    edges = floor.edge_set
    assert (1, 2) in edges
    assert (2, 1) in edges
    assert (2, 3) in edges
    assert (3, 2) in edges

    adj = floor.adjacency_matrix
    expected = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=int)
    assert np.array_equal(adj, expected)


def test_pseudo_room_creation() -> None:
    """Test that pseudo-rooms are created correctly from area."""
    r1 = _make_room(1, "PseudoRoom", area=25.0)

    floor = Floor(floor_number=1, rooms=[r1])
    floor.add_pseudo_rooms()

    assert len(floor.pseudo_rooms) == 1
    pseudo_room = floor.pseudo_rooms[0]
    assert pseudo_room.room_id == r1.room_id
    assert pseudo_room.name == r1.name
    assert pseudo_room.area == r1.area
    assert pseudo_room.walls is not None


def test_invalid_pseudo_room_raises() -> None:
    """Test that invalid pseudo-rooms raise an InvalidRoomError."""
    r1 = _make_room(1, "InvalidPseudoRoom", area=5.0)
    r1.area = -5.0  # Manually set an invalid negative area

    floor = Floor(floor_number=1, rooms=[r1])

    with pytest.raises(InvalidRoomError) as exc_info:
        floor.add_pseudo_rooms()
    assert "Pseudo-room must have a valid positive area" in str(exc_info.value)


def test_psedo_room_skips_spatial_room() -> None:
    """Test that existing spatial rooms are not converted to pseudo-rooms."""
    r1 = Room(
        room_id=1,
        name="SpatialRoom",
        building="B1",
        floor=1,
        contents=[],
        doors=[],
        walls=[
            Wall((0, 0), (0, 1)),
            Wall((0, 1), (1, 1)),
            Wall((1, 1), (1, 0)),
            Wall((1, 0), (0, 0)),
        ],
    )

    floor = Floor(floor_number=1, rooms=[r1])
    floor.add_pseudo_rooms()

    assert len(floor.pseudo_rooms) == 0


def test_locate_room_by_position() -> None:
    """Test locating a room by a given position."""
    r1 = Room(
        room_id=1,
        name="Room1",
        building="B1",
        floor=1,
        contents=[],
        doors=[],
        walls=[
            Wall((0, 0), (0, 2)),
            Wall((0, 2), (2, 2)),
            Wall((2, 2), (2, 0)),
            Wall((2, 0), (0, 0)),
        ],
    )
    r2 = Room(
        room_id=2,
        name="Room2",
        building="B1",
        floor=1,
        contents=[],
        doors=[],
        walls=[
            Wall((3, 3), (3, 5)),
            Wall((3, 5), (5, 5)),
            Wall((5, 5), (5, 3)),
            Wall((5, 3), (3, 3)),
        ],
    )

    floor = Floor(floor_number=1, rooms=[r1, r2])

    room_found = floor.find_room_by_location((1.0, 1.0))
    assert room_found is r1

    room_found = floor.find_room_by_location((4.0, 4.0))
    assert room_found is r2

    room_found = floor.find_room_by_location((6.0, 6.0))
    assert room_found is None
