"""Tests for the Space module."""

import logging

import numpy as np
import pytest

from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.space import (
    check_if_location_reached,
    get_room,
    propose_new_coordinates,
)
from amr_hub_abm.space.wall import Wall


@pytest.fixture
def sample_rooms() -> list[Room]:
    """Fixture to create sample rooms for testing."""
    walls_room1 = [
        Wall(start=(0, 0), end=(0, 10)),
        Wall(start=(0, 10), end=(10, 10)),
        Wall(start=(10, 10), end=(10, 0)),
        Wall(start=(10, 0), end=(0, 0)),
    ]
    room1 = Room(
        room_id=1,
        name="Room 1",
        building="Building A",
        floor=1,
        walls=walls_room1,
        doors=[],
        contents=[],
        rng_generator=np.random.default_rng(),
    )

    walls_room2 = [
        Wall(start=(20, 20), end=(20, 30)),
        Wall(start=(20, 30), end=(30, 30)),
        Wall(start=(30, 30), end=(30, 20)),
        Wall(start=(30, 20), end=(20, 20)),
    ]
    room2 = Room(
        room_id=2,
        name="Room 2",
        building="Building A",
        floor=1,
        walls=walls_room2,
        doors=[],
        contents=[],
        rng_generator=np.random.default_rng(),
    )

    walls_room3 = [
        Wall(start=(40, 40), end=(40, 50)),
        Wall(start=(40, 50), end=(50, 50)),
        Wall(start=(50, 50), end=(50, 40)),
        Wall(start=(50, 40), end=(40, 40)),
    ]
    room3 = Room(
        room_id=3,
        name="Room 3",
        building="Building B",
        floor=2,
        walls=walls_room3,
        doors=[],
        contents=[],
        rng_generator=np.random.default_rng(),
    )

    return [room1, room2, room3]


def test_get_room_location_inside(sample_rooms: list[Room]) -> None:
    """Test that get_room returns the correct room for a location inside a room."""
    location_inside_room1 = Location(x=5, y=5, floor=1, building="Building A")
    room = get_room(location_inside_room1, sample_rooms)
    assert room is not None
    assert room.room_id == 1

    location_inside_room2 = Location(x=25, y=25, floor=1, building="Building A")
    room = get_room(location_inside_room2, sample_rooms)
    assert room is not None
    assert room.room_id == 2

    location_inside_room3 = Location(x=45, y=45, floor=2, building="Building B")
    room = get_room(location_inside_room3, sample_rooms)
    assert room is not None
    assert room.room_id == 3


def test_get_room_location_outside(sample_rooms: list[Room]) -> None:
    """Test that get_room returns None for a location outside all rooms."""
    location_outside = Location(x=15, y=15, floor=1, building="Building A")
    room = get_room(location_outside, sample_rooms)
    assert room is None

    location_outside_building = Location(x=5, y=5, floor=1, building="Building C")
    room = get_room(location_outside_building, sample_rooms)
    assert room is None

    location_outside_floor = Location(x=5, y=5, floor=2, building="Building A")
    room = get_room(location_outside_floor, sample_rooms)
    assert room is None


def test_check_if_location_reached() -> None:
    """Test the check_if_location_reached function."""
    current_location = Location(x=5, y=5, floor=1, building="Building A")
    target_location = Location(x=5.1, y=5.1, floor=1, building="Building A")
    interaction_radius = 0.2

    assert check_if_location_reached(
        current_location, target_location, interaction_radius
    )

    target_location_far = Location(x=6, y=6, floor=1, building="Building A")
    assert not check_if_location_reached(
        current_location, target_location_far, interaction_radius
    )

    target_location_different_floor = Location(
        x=5.1, y=5.1, floor=2, building="Building A"
    )
    assert not check_if_location_reached(
        current_location, target_location_different_floor, interaction_radius
    )

    target_location_different_building = Location(
        x=5.1, y=5.1, floor=1, building="Building B"
    )
    assert not check_if_location_reached(
        current_location, target_location_different_building, interaction_radius
    )


def test_propose_new_coordinates() -> None:
    """Test the propose_new_coordinates function."""
    current_location = (5, 5)
    movement_speed = 1.0
    heading = 0.0  # Heading in radians (0 means moving to the right)
    stochasticity = 0.1  # Small randomness in movement

    new_location = propose_new_coordinates(
        current_location,
        heading,
        movement_speed,
        stochasticity,
        rng_generator=np.random.default_rng(),
    )

    # Check that the new location is a tuple of two floats
    assert isinstance(new_location, tuple)
    assert len(new_location) == 2
    assert all(isinstance(coord, float) for coord in new_location)


def test_propose_new_coordinates_with_negative_stochasticity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the propose_new_coordinates function with negative stochasticity."""
    current_location = (5, 5)
    movement_speed = 1.0
    heading = np.pi / 2  # Heading in radians (90 degrees, moving up)
    stochasticity = -0.1  # Negative randomness in movement

    with caplog.at_level(logging.WARNING):
        new_location = propose_new_coordinates(
            current_location,
            heading,
            movement_speed,
            stochasticity,
            rng_generator=np.random.default_rng(),
        )

    # Check that the new location is a tuple of two floats
    assert isinstance(new_location, tuple)
    assert len(new_location) == 2
    assert all(isinstance(coord, float) for coord in new_location)

    # Check that a warning was logged
    assert "Stochasticity is negative" in caplog.text

    new_location = propose_new_coordinates(
        current_location,
        heading,
        movement_speed,
        stochasticity,
        rng_generator=np.random.default_rng(),
    )

    # Check that the new location is a tuple of two floats
    assert isinstance(new_location, tuple)
    assert len(new_location) == 2
    assert all(isinstance(coord, float) for coord in new_location)
