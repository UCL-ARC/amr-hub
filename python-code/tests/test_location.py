"""Tests for the Location class in the space module."""

import pytest

from amr_hub_abm.exceptions import InvalidDistanceError
from amr_hub_abm.space.location import Building, Location


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

    loc1 = Location(x=0.0, y=0.0, floor=1, building=building_a)
    loc2 = Location(x=3.0, y=4.0, floor=1, building=building_b)

    with pytest.raises(InvalidDistanceError) as exc_info:
        loc1.distance_to(loc2)

    err_string = "Invalid distance calculation between buildings: "

    assert str(exc_info.value) == f"{err_string}{building_a} and {building_b}."
