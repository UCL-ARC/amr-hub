"""Tests for the Room class in the AMR Hub ABM simulation."""

from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pytest
import shapely

from amr_hub_abm.agent import Agent
from amr_hub_abm.exceptions import InvalidRoomError, SimulationModeError
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.content import Content
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.location import Location
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
def empty_contents() -> list[Content]:
    """Fixture for empty room contents."""
    return []


@pytest.fixture
def empty_doors() -> list[Door]:
    """Fixture for an empty door list."""
    return []


@pytest.fixture
def room_with_internal_walls(
    test_building: Building, empty_doors: list[Door], empty_contents: list[Content]
) -> Room:
    """Fixture for a room with internal walls."""
    walls = [
        Wall(start=(0, 0), end=(5, 0)),
        Wall(start=(5, 0), end=(5, 5)),
        Wall(start=(5, 5), end=(0, 5)),
        Wall(start=(0, 5), end=(0, 0)),
        Wall(start=(1, 1), end=(1, 2)),
        Wall(start=(1, 2), end=(2, 2)),
        Wall(start=(2, 2), end=(2, 1)),
        Wall(start=(2, 1), end=(1, 1)),
    ]

    return Room(
        room_id=1,
        name="Room with Internal Walls",
        building=test_building.name,
        floor=1,
        walls=walls,
        doors=empty_doors,
        contents=empty_contents,
    )


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
    assert len(simple_room.walls) == 4


def test_complex_room_with_internal_walls(room_with_internal_walls: Room) -> None:
    """Test creating a room with internal walls."""
    point1 = shapely.geometry.Point(3, 3)
    point2 = shapely.geometry.Point(1.5, 1.5)

    assert room_with_internal_walls is not None
    assert room_with_internal_walls.region.contains(point1)
    assert not room_with_internal_walls.region.contains(point2)


def test_invalid_room_no_walls_or_area(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room with neither walls nor area defined."""
    with pytest.raises(SimulationModeError) as exc_info:
        Room(
            room_id=1,
            name="Invalid Room",
            building=test_building.name,
            floor=1,
            walls=None,
            doors=empty_doors,
            contents=empty_contents,
        )
    assert "Either walls or area must be provided to define a room." in str(
        exc_info.value
    )


def test_invalid_room_both_walls_and_area(
    test_building: Building,
    simple_walls: list[Wall],
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room with both walls and area defined."""
    with pytest.raises(SimulationModeError) as exc_info:
        Room(
            room_id=1,
            name="Invalid Room",
            building=test_building.name,
            floor=1,
            walls=simple_walls,
            area=25.0,
            doors=empty_doors,
            contents=empty_contents,
        )
    assert "Provide either walls or area, not both, to define a room." in str(
        exc_info.value
    )


def test_invalid_room_negative_area(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room with negative area."""
    with pytest.raises(InvalidRoomError) as exc_info:
        Room(
            room_id=1,
            name="Invalid Room",
            building=test_building.name,
            floor=1,
            area=-10.0,
            doors=empty_doors,
            contents=empty_contents,
        )
    assert "Room area must be positive." in str(exc_info.value)


def test_invalid_region_creation(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room with topological map that does not form a valid polygon."""
    room = Room(
        room_id=1,
        name="Topological Room",
        building=test_building.name,
        floor=1,
        area=10.0,
        doors=empty_doors,
        contents=empty_contents,
    )
    with pytest.raises(InvalidRoomError) as exc_info:
        room.form_region()
    assert "Cannot form region without walls." in str(exc_info.value)


def test_invalid_plot_creation(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room with topological map that does not form a valid polygon."""
    room = Room(
        room_id=1,
        name="Topological Room",
        building=test_building.name,
        floor=1,
        area=10.0,
        doors=empty_doors,
        contents=empty_contents,
    )

    fig = plt.figure()
    ax = fig.add_subplot(111)
    with pytest.raises(SimulationModeError) as exc_info:
        room.plot(ax=ax)
    assert "Cannot plot room without walls." in str(exc_info.value)


def test_invalid_polygon_hash_creation(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room with topological map that does not form a valid polygon."""
    room = Room(
        room_id=1,
        name="Topological Room",
        building=test_building.name,
        floor=1,
        area=10.0,
        doors=empty_doors,
        contents=empty_contents,
    )

    with pytest.raises(SimulationModeError) as exc_info:
        room.create_polygon_hash()
    assert "Cannot create polygon hash without walls." in str(exc_info.value)


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


def test_unconnected_walls() -> None:
    """Test creating a room with unconnected walls."""
    walls = [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(1, 0), end=(1, 5)),  # Not connected to the first wall
        Wall(start=(2, 0), end=(2, 5)),
        Wall(start=(3, 0), end=(3, 5)),
    ]

    with pytest.raises(InvalidRoomError) as exc_info:
        Room(
            room_id=8,
            name="Room with Unconnected Walls",
            building="Test Building",
            floor=1,
            walls=walls,
            doors=[],
            contents=[],
        )
    assert "The walls do not form a valid closed region" in str(exc_info.value)


def test_plot_room(simple_room: Room) -> None:
    """Test plotting a room."""
    fig, ax = plt.subplots()
    simple_room.plot(ax=ax)
    plt.close(fig)  # Close the plot to avoid displaying during tests


def test_plot_room_with_agent_inside(simple_room: Room) -> None:
    """Test plotting includes agents located inside the room."""
    fig, ax = plt.subplots()
    agent = Agent(
        idx=1,
        location=Location(1.0, 1.0, floor=1, building=simple_room.building),
        heading=0.0,
    )
    with patch.object(agent, "plot_agent") as mock_plot_agent:
        simple_room.plot(ax=ax, agents=[agent])
        mock_plot_agent.assert_called_once()

    plt.close(fig)


def test_plot_room_skips_agent_outside(simple_room: Room) -> None:
    """Test plotting skips agents located outside the room."""
    fig, ax = plt.subplots()
    agent = Agent(
        idx=2,
        location=Location(6.0, 6.0, floor=1, building=simple_room.building),
        heading=0.0,
    )

    with patch.object(agent, "plot_agent") as mock_plot_agent:
        simple_room.plot(ax=ax, agents=[agent])
        mock_plot_agent.assert_not_called()
    plt.close(fig)


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


def test_room_hash_equality(simple_room: Room, room_4x4: Room) -> None:
    """Test the hash and equality methods of the Room class."""
    another_simple_room = Room(
        room_id=simple_room.room_id,
        name=simple_room.name,
        building=simple_room.building,
        floor=simple_room.floor,
        walls=simple_room.walls,
        doors=simple_room.doors,
        contents=simple_room.contents,
    )

    assert hash(simple_room) == hash(another_simple_room)
    assert simple_room == another_simple_room
    assert simple_room != room_4x4


def test_room_name_hash(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room defined by name and area."""
    room = Room(
        room_id=8,
        name="Named Room",
        building=test_building.name,
        floor=1,
        area=30.0,
        doors=empty_doors,
        contents=empty_contents,
    )

    assert room.room_hash is not None


def test_room_polygon_hash(
    test_building: Building,
    simple_walls: list[Wall],
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test creating a room defined by walls."""
    room = Room(
        room_id=9,
        name="Polygon Room",
        building=test_building.name,
        floor=1,
        walls=simple_walls,
        doors=empty_doors,
        contents=empty_contents,
    )

    assert room.room_hash is not None


def test_room_hash_type_error(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test equality comparison with a non-Room object."""
    room = Room(
        room_id=10,
        name="Test Room",
        building=test_building.name,
        floor=1,
        area=20.0,
        doors=empty_doors,
        contents=empty_contents,
    )

    assert room != "Not a Room Object"


def test_room_contains_point(room_4x4: Room) -> None:
    """Test the contains_point method of the Room class."""
    inside_point = (2, 2)
    outside_point = (5.5, 5.5)

    assert room_4x4.contains_point(inside_point) is True
    assert room_4x4.contains_point(outside_point) is False


def test_room_contains_point_topology_error(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test contains_point method raises error when region is not defined."""
    room = Room(
        room_id=11,
        name="Topology Error Room",
        building=test_building.name,
        floor=1,
        area=15.0,
        doors=empty_doors,
        contents=empty_contents,
    )

    with pytest.raises(SimulationModeError) as exc_info:
        room.contains_point((1, 1))
    assert "Cannot check point containment without walls." in str(exc_info.value)


def test_room_get_random_point(simple_room: Room) -> None:
    """Test the get_random_point method of the Room class."""
    random_point = simple_room.get_random_point()
    assert simple_room.contains_point(random_point) is True
    rng = np.random.default_rng()
    random_point = simple_room.get_random_point(rng=rng)


def test_room_get_random_point_topology_error(
    test_building: Building,
    empty_doors: list[Door],
    empty_contents: list[Content],
) -> None:
    """Test get_random_point method raises error when region is not defined."""
    room = Room(
        room_id=12,
        name="Topology Error Room",
        building=test_building.name,
        floor=1,
        area=20.0,
        doors=empty_doors,
        contents=empty_contents,
    )

    with pytest.raises(SimulationModeError) as exc_info:
        room.get_random_point()
    assert "Cannot get random point without walls." in str(exc_info.value)


class AlwaysLowRNG:
    """Mock RNG that always returns the lower bound."""

    def uniform(self, low: float, _: float) -> float:
        """Uniformly return the low bound."""
        return low  # always pick min bound -> boundary point


def test_get_random_point_raises_after_max_attempts(
    square_4x4_walls: list[Wall],
) -> None:
    """Test that get_random_point raises an error after max attempts."""
    room = Room(
        room_id=13,
        name="Test Room",
        building="Test Building",
        floor=1,
        walls=square_4x4_walls,
        doors=[],
        contents=[],
    )

    rng = AlwaysLowRNG()

    with pytest.raises(SimulationModeError) as exc_info:
        room.get_random_point(rng=rng, max_attempts=10)  # type: ignore[arg-type]
    assert "Failed to find a random point within the room after 10 attempts." in str(
        exc_info.value
    )


def test_room_get_door_access_point(
    test_building: Building,
    simple_walls: list[Wall],
    empty_contents: list[Content],
) -> None:
    """Test the get_door_access_point method of the Room class."""
    doors = [
        Door(
            start=(0, 2),
            end=(0, 3),
            open=True,
            connecting_rooms=(1, 2),
            access_control=(True, True),
        )
    ]

    room = Room(
        room_id=14,
        name="Room with Door",
        building=test_building.name,
        floor=1,
        walls=simple_walls,
        doors=doors,
        contents=empty_contents,
    )

    door, access_point = room.get_door_access_point()
    assert door == doors[0]
    assert isinstance(access_point, tuple)
    assert len(access_point) == 2


def test_room_get_door_access_point_no_doors(
    test_building: Building,
    simple_walls: list[Wall],
    empty_contents: list[Content],
) -> None:
    """Test get_door_access_point raises error when no doors are present."""
    room = Room(
        room_id=15,
        name="Room without Doors",
        building=test_building.name,
        floor=1,
        walls=simple_walls,
        doors=[],
        contents=empty_contents,
    )

    with pytest.raises(InvalidRoomError) as exc_info:
        room.get_door_access_point()
    assert "has no doors for access." in str(exc_info.value)


def test_room_get_door_access_point_multiple_doors(
    test_building: Building,
    simple_walls: list[Wall],
    empty_contents: list[Content],
) -> None:
    """Test get_door_access_point with multiple doors."""
    doors = [
        Door(
            start=(0, 1),
            end=(0, 2),
            open=True,
            connecting_rooms=(1, 2),
            access_control=(True, True),
        ),
        Door(
            start=(0, 3),
            end=(0, 4),
            open=True,
            connecting_rooms=(1, 3),
            access_control=(True, True),
        ),
    ]

    room = Room(
        room_id=16,
        name="Room with Multiple Doors",
        building=test_building.name,
        floor=1,
        walls=simple_walls,
        doors=doors,
        contents=empty_contents,
    )

    with pytest.raises(InvalidRoomError) as exc_info:
        room.get_door_access_point()

    assert "not supported" in str(exc_info.value)
