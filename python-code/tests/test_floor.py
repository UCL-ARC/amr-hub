"""Tests for the Floor class in amr_hub_abm.space.floor module."""

import numpy as np
import pytest

from amr_hub_abm.exceptions import InvalidRoomError
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.room import Room


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
    door_id: int,
    a: int,
    b: int,
    start: tuple[float, float] = (0.0, 0.0),
    end: tuple[float, float] = (1.0, 0.0),
) -> Door:
    return Door(
        door_id=door_id,
        open=True,
        connecting_rooms=(a, b),
        access_control=(True, True),
        start=start,
        end=end,
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
    d12 = _make_door(1, 1, 2, start=(0.0, 0.0), end=(1.0, 0.0))
    d23 = _make_door(2, 2, 3, start=(1.0, 0.0), end=(2.0, 0.0))

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
