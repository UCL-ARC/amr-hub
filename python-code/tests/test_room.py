"""Tests for the Room class in the AMR Hub ABM simulation."""

from pathlib import Path

import matplotlib.pyplot as plt
import pytest
import shapely

from amr_hub_abm.exceptions import InvalidRoomError
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.content import Content
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_building() -> Building:
    """Fixture for a test building."""
    return Building(name="Test Building", floors=[])


@pytest.fixture
def simple_walls() -> list[Wall]:
    """Fixture for a simple square room (5x5)."""
    return [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        Wall(start=(5, 0), end=(0, 0)),
    ]


@pytest.fixture
def square_4x4_walls() -> list[Wall]:
    """Fixture for a 4x4 square room."""
    return [
        Wall(start=(0, 0), end=(0, 4)),
        Wall(start=(0, 4), end=(4, 4)),
        Wall(start=(4, 4), end=(4, 0)),
        Wall(start=(4, 0), end=(0, 0)),
    ]


@pytest.fixture
def room_with_internal_walls() -> list[Wall]:
    """Fixture for a room with internal walls."""
    return [
        Wall(start=(0, 0), end=(5, 0)),
        Wall(start=(5, 0), end=(5, 5)),
        Wall(start=(5, 5), end=(0, 5)),
        Wall(start=(0, 5), end=(0, 0)),
        Wall(start=(1, 1), end=(1, 2)),
        Wall(start=(1, 2), end=(2, 2)),
        Wall(start=(2, 2), end=(2, 1)),
        Wall(start=(2, 1), end=(1, 1)),
    ]


@pytest.fixture
def room_with_door_on_left_wall() -> tuple[list[Wall], list[Door]]:
    """Fixture for a room with a door on the left wall."""
    walls = [
        Wall(start=(0, 0), end=(0, 2)),
        Wall(start=(0, 3), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        Wall(start=(5, 0), end=(0, 0)),
    ]

    doors = [
        Door(
            door_id=1,
            start=(0, 2),
            end=(0, 3),
            open=True,
            connecting_rooms=(1, 2),
            access_control=(True, True),
        )
    ]

    return walls, doors


@pytest.fixture
def empty_contents() -> list[Content]:
    """Fixture for empty room contents."""
    return []


@pytest.fixture
def empty_doors() -> list[Door]:
    """Fixture for an empty door list."""
    return []


@pytest.fixture
def simple_room(
    test_building: Building,
    simple_walls: list[Wall],
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> Room:
    """Fixture for a simple valid room."""
    return Room(
        room_id=1,
        name="Simple Room",
        building=test_building.name,
        floor=1,
        walls=simple_walls,
        doors=empty_doors,
        contents=empty_contents,
    )


@pytest.fixture
def room_4x4(
    test_building: Building,
    square_4x4_walls: list[Wall],
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> Room:
    """Fixture for a 4x4 square room."""
    return Room(
        room_id=6,
        name="4x4 Room",
        building=test_building.name,
        floor=1,
        walls=square_4x4_walls,
        doors=empty_doors,
        contents=empty_contents,
    )


# ============================================================================
# Tests
# ============================================================================


def test_simple_room_creation(simple_room: Room) -> None:
    """Test creating a simple valid room."""
    assert simple_room.room_id == 1
    assert simple_room.walls is not None
    assert len(simple_room.walls) == 4  # noqa: PLR2004


def test_complex_room_with_internal_walls(
    test_building: Building,
    room_with_internal_walls: list[Wall],
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room with internal walls."""
    room = Room(
        room_id=1,
        name="Room with Internal Walls",
        building=test_building.name,
        floor=1,
        walls=room_with_internal_walls,
        doors=empty_doors,
        contents=empty_contents,
    )

    # check if a point is inside the room
    point1 = shapely.geometry.Point(3, 3)
    point2 = shapely.geometry.Point(1.5, 1.5)

    assert room.region.contains(point1)
    assert not room.region.contains(point2)


def test_invalid_room_too_few_walls(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room with too few walls."""
    walls = [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
    ]

    with pytest.raises(InvalidRoomError) as exc_info:
        Room(
            room_id=2,
            name="Room with Too Few Walls",
            building=test_building.name,
            floor=1,
            walls=walls,
            doors=empty_doors,
            contents=empty_contents,
        )
    assert "A room must have at least 3 walls to form a closed region." in str(
        exc_info.value
    )


def test_invalid_room_non_closed_walls(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room with walls that do not form a closed region."""
    walls = [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        # Missing wall to close the room
    ]

    with pytest.raises(InvalidRoomError) as exc_info:
        Room(
            room_id=3,
            name="Room with Non-Closed Walls",
            building=test_building.name,
            floor=1,
            walls=walls,
            doors=empty_doors,
            contents=empty_contents,
        )
    assert "The walls do not form a valid closed region." in str(exc_info.value)


def test_plot_room(simple_room: Room) -> None:
    """Test plotting a room."""
    fig, ax = plt.subplots()
    simple_room.plot(ax=ax)
    plt.close(fig)  # Close the plot to avoid displaying during tests


def test_room_with_doors(
    test_building: Building, empty_contents: list[Content]
) -> None:
    """Test creating and plotting a room with doors."""
    walls, doors = (
        [
            Wall(start=(0, 0), end=(0, 2)),
            Wall(start=(0, 3), end=(0, 5)),
            Wall(start=(0, 5), end=(5, 5)),
            Wall(start=(5, 5), end=(5, 0)),
            Wall(start=(5, 0), end=(0, 0)),
        ],
        [
            Door(
                door_id=1,
                start=(0, 2),
                end=(0, 3),
                open=True,
                connecting_rooms=(1, 2),
                access_control=(True, True),
            )
        ],
    )

    room = Room(
        room_id=5,
        name="Room with Door",
        building=test_building.name,
        floor=1,
        walls=walls,
        doors=doors,
        contents=empty_contents,
    )

    assert len(room.doors) == 1


def test_room_region_area_calculation(room_4x4: Room) -> None:
    """Test the region calculation of a room."""
    expected_area = 16.0  # 4x4 square
    assert room_4x4.area == expected_area


def test_room_plotting_with_doors(
    test_building: Building, empty_contents: list[Content]
) -> None:
    """Test plotting a room with doors."""
    walls = [
        Wall(start=(0, 0), end=(0, 3)),
        Wall(start=(0, 4), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        Wall(start=(5, 0), end=(0, 0)),
    ]

    doors = [
        Door(
            door_id=1,
            start=(0, 3),
            end=(0, 4),
            open=True,
            connecting_rooms=(1, 2),
            access_control=(True, True),
        )
    ]

    room = Room(
        room_id=7,
        name="Room with Door",
        building=test_building.name,
        floor=1,
        walls=walls,
        doors=doors,
        contents=empty_contents,
    )

    fig, ax = plt.subplots()
    room.plot(ax=ax)
    if not Path("tests/output/").exists():
        Path("tests/output/").mkdir(parents=True, exist_ok=True)
    plt.savefig("tests/output/room_with_door_plot.png")
    plt.close(fig)  # Close the plot to avoid displaying during tests
