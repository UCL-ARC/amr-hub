"""Tests for the Room class in the AMR Hub ABM simulation."""

import matplotlib.pyplot as plt
import pytest
import shapely

from amr_hub_abm.exceptions import InvalidRoomError
from amr_hub_abm.space import Building, Content, SpatialDoor, SpatialRoom, Wall


def test_simple_room_creation() -> None:
    """Test creating a simple valid room."""
    walls = [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        Wall(start=(5, 0), end=(0, 0)),
    ]

    doors: list[SpatialDoor] = []
    contents: list[Content] = []

    room = SpatialRoom(
        room_id=1,
        building=Building(name="Test Building"),
        floor=1,
        walls=walls,
        doors=doors,
        contents=contents,
    )
    assert room.room_id == 1
    assert len(room.walls) == 4  # noqa: PLR2004


def test_complex_room_with_internal_walls() -> None:
    """Test creating a room with internal walls."""
    wall1 = Wall(start=(0, 0), end=(5, 0))
    wall2 = Wall(start=(5, 0), end=(5, 5))
    wall3 = Wall(start=(5, 5), end=(0, 5))
    wall4 = Wall(start=(0, 5), end=(0, 0))

    wall5 = Wall(start=(1, 1), end=(1, 2))
    wall6 = Wall(start=(1, 2), end=(2, 2))
    wall7 = Wall(start=(2, 2), end=(2, 1))
    wall8 = Wall(start=(2, 1), end=(1, 1))

    room = SpatialRoom(
        room_id=1,
        building=Building(name="Test Building"),
        floor=1,
        walls=[wall1, wall2, wall3, wall4, wall5, wall6, wall7, wall8],
        doors=[],
        contents=[],
    )

    # check if a point is inside the room
    point1 = shapely.geometry.Point(3, 3)
    point2 = shapely.geometry.Point(1.5, 1.5)

    assert room.region.contains(point1)
    assert not room.region.contains(point2)


def test_invalid_room_too_few_walls() -> None:
    """Test creating a room with too few walls."""
    walls = [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
    ]

    doors: list[SpatialDoor] = []
    contents: list[Content] = []

    with pytest.raises(InvalidRoomError) as exc_info:
        SpatialRoom(
            room_id=2,
            building=Building(name="Test Building"),
            floor=1,
            walls=walls,
            doors=doors,
            contents=contents,
        )
    assert "A room must have at least 3 walls to form a closed region." in str(
        exc_info.value
    )


def test_invalid_room_non_closed_walls() -> None:
    """Test creating a room with walls that do not form a closed region."""
    walls = [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        # Missing wall to close the room
    ]

    doors: list[SpatialDoor] = []
    contents: list[Content] = []

    with pytest.raises(InvalidRoomError) as exc_info:
        SpatialRoom(
            room_id=3,
            building=Building(name="Test Building"),
            floor=1,
            walls=walls,
            doors=doors,
            contents=contents,
        )
    assert "The walls do not form a valid closed region." in str(exc_info.value)


def test_plot_room() -> None:
    """Test plotting a room."""
    walls = [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        Wall(start=(5, 0), end=(0, 0)),
    ]

    doors: list[SpatialDoor] = []
    contents: list[Content] = []

    room = SpatialRoom(
        room_id=4,
        building=Building(name="Test Building"),
        floor=1,
        walls=walls,
        doors=doors,
        contents=contents,
    )
    fig, ax = plt.subplots()
    room.plot(ax=ax)
    plt.close(fig)  # Close the plot to avoid displaying during tests


def test_room_with_doors() -> None:
    """Test creating and plotting a room with doors."""
    walls = [
        Wall(start=(0, 0), end=(0, 2)),
        Wall(start=(0, 3), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        Wall(start=(5, 0), end=(0, 0)),
    ]

    door1 = SpatialDoor(
        start=(0, 2),
        end=(0, 3),
        open=True,
        connecting_rooms=(1, 2),
        access_control=(True, True),
    )  # Door on the left wall

    contents: list[Content] = []

    room = SpatialRoom(
        room_id=5,
        building=Building(name="Test Building"),
        floor=1,
        walls=walls,
        doors=[door1],
        contents=contents,
    )

    assert len(room.doors) == 1


def test_room_region_area_calculation() -> None:
    """Test the region calculation of a room."""
    walls = [
        Wall(start=(0, 0), end=(0, 4)),
        Wall(start=(0, 4), end=(4, 4)),
        Wall(start=(4, 4), end=(4, 0)),
        Wall(start=(4, 0), end=(0, 0)),
    ]

    doors: list[SpatialDoor] = []
    contents: list[Content] = []

    room = SpatialRoom(
        room_id=6,
        building=Building(name="Test Building"),
        floor=1,
        walls=walls,
        doors=doors,
        contents=contents,
    )

    expected_area = 16.0  # 4x4 square
    assert room.region.area == expected_area


def test_room_plotting_with_doors() -> None:
    """Test plotting a room with doors."""
    walls = [
        Wall(start=(0, 0), end=(0, 3)),
        Wall(start=(0, 4), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        Wall(start=(5, 0), end=(0, 0)),
    ]

    door1 = SpatialDoor(
        start=(0, 3),
        end=(0, 4),
        open=True,
        connecting_rooms=(1, 2),
        access_control=(True, True),
    )  # Door on the left wall

    contents: list[Content] = []

    room = SpatialRoom(
        room_id=7,
        building=Building(name="Test Building"),
        floor=1,
        walls=walls,
        doors=[door1],
        contents=contents,
    )

    fig, ax = plt.subplots()
    room.plot(ax=ax)
    plt.close(fig)  # Close the plot to avoid displaying during tests
