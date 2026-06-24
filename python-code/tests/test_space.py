"""Test suite for space functions."""

# ruff: noqa: PLR2004

import numpy as np
import pytest

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.space import SpatialQuery
from amr_hub_abm.space.wall import Wall


@pytest.fixture
def rng_generator() -> np.random.Generator:
    """Fixture providing a random number generator."""
    return np.random.default_rng(seed=42)


def test_get_room(rng_generator: np.random.Generator) -> None:
    """Test identifying the room containing a given location via the engine."""
    # Room 1: x from 0 to 10
    walls1 = [
        Wall((0, 0), (10, 0)),
        Wall((10, 0), (10, 10)),
        Wall((10, 10), (0, 10)),
        Wall((0, 10), (0, 0)),
    ]
    room1 = Room(
        room_id=1,
        name="Room A",
        building="A",
        floor=1,
        walls=walls1,
        contents=[],
        doors=[],
        rng_generator=rng_generator,
    )

    # Room 2: x from 10 to 20
    walls2 = [
        Wall((10, 0), (20, 0)),
        Wall((20, 0), (20, 10)),
        Wall((20, 10), (10, 10)),
        Wall((10, 10), (10, 0)),
    ]
    room2 = Room(
        room_id=2,
        name="Room B",
        building="A",
        floor=1,
        walls=walls2,
        contents=[],
        doors=[],
        rng_generator=rng_generator,
    )

    # Build the strict, type-safe hierarchy
    floor1 = Floor(floor_number=1, rooms=[room1, room2])
    building1 = Building(name="A", floors=[floor1])

    # Initialize the engine with the strict hierarchy
    engine = SpatialQuery(space=[building1])

    # Test Agent 1 inside Room 1
    loc_in_room1 = Location(x=5.0, y=5.0, floor=1, building="A")
    agent1 = Agent(
        idx=1, location=loc_in_room1, heading_rad=0.0, rng_generator=rng_generator
    )

    assert engine.get_room(agent1) == room1

    # Test Agent 2 inside Room 2
    loc_in_room2 = Location(x=15.0, y=5.0, floor=1, building="A")
    agent2 = Agent(
        idx=2, location=loc_in_room2, heading_rad=0.0, rng_generator=rng_generator
    )

    assert engine.get_room(agent2) == room2


def test_check_if_location_reached() -> None:
    """Test checking if an agent has reached a target location."""
    loc1 = Location(x=0.0, y=0.0, floor=1, building="A")
    loc2 = Location(x=3.0, y=4.0, floor=1, building="A")
    loc3 = Location(x=0.0, y=0.0, floor=2, building="A")

    engine = SpatialQuery(space=[])

    assert engine.is_target_reached(loc1, loc2, radius=6.0) is True
    assert engine.is_target_reached(loc1, loc2, radius=4.0) is False
    assert engine.is_target_reached(loc1, loc3, radius=10.0) is False


def test_propose_new_coordinates(rng_generator: np.random.Generator) -> None:
    """Test proposing new coordinates based on heading and speed."""
    coords = (0.0, 0.0)
    heading_rad = 0.0
    movement_speed = 1.0
    stochasticity = 0.0

    engine = SpatialQuery(space=[])

    new_coords = engine.propose_new_coordinates(
        coords, heading_rad, movement_speed, stochasticity, rng_generator
    )
    assert np.isclose(new_coords[0], 1.0)
    assert np.isclose(new_coords[1], 0.0)


def test_estimate_time_to_reach_location(rng_generator: np.random.Generator) -> None:
    """Test estimating the time required to reach a target location."""
    current_loc = Location(x=0.0, y=0.0, floor=0, building="A")
    target_loc = Location(x=3.0, y=4.0, floor=0, building="A")

    # Create an agent to hold the speed and current location
    agent = Agent(
        idx=1,
        location=current_loc,
        heading_rad=0.0,
        rng_generator=rng_generator,
        movement_speed=2.0,
    )

    engine = SpatialQuery(space=[])

    assert engine.estimate_time_to_reach_location(agent, target_loc) == 2.5
