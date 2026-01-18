"""Tests for the Location class in the space module."""

import pytest

from amr_hub_abm.exceptions import InvalidDistanceError
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall


@pytest.fixture
def sample_room() -> Room:
    """Create a sample room for testing."""
    walls = [
        Wall(start=(0, 0), end=(0, 10)),
        Wall(start=(0, 10), end=(10, 10)),
        Wall(start=(10, 10), end=(10, 0)),
        Wall(start=(10, 0), end=(0, 0)),
    ]
    return Room(
        room_id=1,
        name="Sample Room",
        building="Test Building",
        floor=1,
        walls=walls,
        doors=[],
        contents=[],
    )


def test_location_creation() -> None:
    """Test the creation of a Location instance."""
    location = Location(x=10.0, y=20.0, floor=2)

    expected_x = 10.0
    expected_y = 20.0
    expected_floor = 2

    assert location.x == expected_x
    assert location.y == expected_y
    assert location.floor == expected_floor


def test_location_move() -> None:
    """Test moving a Location to new coordinates."""
    location = Location(x=0.0, y=0.0, floor=0)
    location.move(new_x=15.0, new_y=25.0, new_floor=1)

    expected_x = 15.0
    expected_y = 25.0
    expected_floor = 1

    assert location.x == expected_x
    assert location.y == expected_y
    assert location.floor == expected_floor


def test_distance_to_same_floor() -> None:
    """Test distance calculation between two locations on the same floor."""
    loc1 = Location(x=0.0, y=0.0, floor=1)
    loc2 = Location(x=3.0, y=4.0, floor=1)

    distance = loc1.distance_to(loc2)

    expected_distance = 5.0  # 3-4-5 triangle

    assert distance == expected_distance


def test_distance_to_different_floors() -> None:
    """Test that distance calculation raises an error for different floors."""
    loc1 = Location(x=0.0, y=0.0, floor=1)
    loc2 = Location(x=3.0, y=4.0, floor=2)

    with pytest.raises(InvalidDistanceError) as exc_info:
        loc1.distance_to(loc2)

    assert (
        str(exc_info.value) == "Invalid distance calculation between floors: 1 and 2."
    )


def test_distance_to_different_buildings() -> None:
    """Test that distance calculation raises an error for different buildings."""
    building_a = Building(name="Building A", floors=[])
    building_b = Building(name="Building B", floors=[])

    loc1 = Location(x=0.0, y=0.0, floor=1, building=building_a.name)
    loc2 = Location(x=3.0, y=4.0, floor=1, building=building_b.name)

    with pytest.raises(InvalidDistanceError) as exc_info:
        loc1.distance_to(loc2)

    err_string = "Invalid distance calculation between buildings: "

    assert (
        str(exc_info.value) == f"{err_string}{building_a.name} and {building_b.name}."
    )


def test_which_room_no_rooms() -> None:
    """Test which_room method when there are no rooms."""
    location = Location(x=5.0, y=5.0, floor=1, building="Test Building")
    rooms: list[Room] = []

    result = location.which_room(rooms)

    assert result is None


def test_which_room_not_in_any_room(sample_room: Room) -> None:
    """Test which_room method when location is not in any room."""
    location = Location(x=50.0, y=50.0, floor=1, building="Test Building")
    rooms = [sample_room]

    result = location.which_room(rooms)

    assert result is None


def test_which_room_in_room(sample_room: Room) -> None:
    """Test which_room method when location is inside a room."""
    location = Location(x=5.0, y=5.0, floor=1, building="Test Building")
    rooms = [sample_room]

    result = location.which_room(rooms)

    assert result is not None
    assert result.room_id == 1
    assert result.name == "Sample Room"


def test_which_room_different_floor(sample_room: Room) -> None:
    """Test which_room method when location is on a different floor than rooms."""
    location = Location(x=5.0, y=5.0, floor=2, building="Test Building")
    rooms = [sample_room]

    result = location.which_room(rooms)

    assert result is None


def test_line_of_sight_no_walls() -> None:
    """Test line of sight when there are no walls."""
    loc1 = Location(x=0.0, y=0.0, floor=1, building="Test Building")
    loc2 = Location(x=10.0, y=10.0, floor=1, building="Test Building")

    result = loc1.check_line_of_sight(loc2, walls=[])

    assert result is True


def test_line_of_sight_with_walls_blocking() -> None:
    """Test line of sight when walls are blocking the view."""
    loc1 = Location(x=0.0, y=0.0, floor=1, building="Test Building")
    loc2 = Location(x=10.0, y=10.0, floor=1, building="Test Building")
    walls = [
        Wall(start=(5.0, 0.0), end=(5.0, 10.0)),  # Vertical wall blocking the line
    ]

    result = loc1.check_line_of_sight(loc2, walls=walls)

    assert result is False


def test_line_of_sight_with_walls_not_blocking() -> None:
    """Test line of sight when walls are not blocking the view."""
    loc1 = Location(x=0.0, y=0.0, floor=1, building="Test Building")
    loc2 = Location(x=10.0, y=10.0, floor=1, building="Test Building")
    walls = [
        Wall(start=(0.0, 5.0), end=(4.0, 5.0)),  # Horizontal wall not blocking the line
    ]

    result = loc1.check_line_of_sight(loc2, walls=walls)

    assert result is True


def test_line_of_sight_different_buildings() -> None:
    """Test line of sight when locations are in different buildings."""
    loc1 = Location(x=0.0, y=0.0, floor=1, building="Building A")
    loc2 = Location(x=10.0, y=10.0, floor=1, building="Building B")

    result = loc1.check_line_of_sight(loc2, walls=[])

    assert result is False


def test_line_of_sight_different_floors() -> None:
    """Test line of sight when locations are on different floors."""
    loc1 = Location(x=0.0, y=0.0, floor=1, building="Test Building")
    loc2 = Location(x=10.0, y=10.0, floor=2, building="Test Building")

    result = loc1.check_line_of_sight(loc2, walls=[])

    assert result is False
