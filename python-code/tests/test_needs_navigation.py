"""Tests for facility routing on the synthetic hospital floorplan."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from amr_hub_abm.agent import needs_navigation
from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.agent.needs_navigation import _door_points, route_to_facility
from amr_hub_abm.read_space_input import SpaceInputReader
from amr_hub_abm.spatial.furniture import ContentType
from amr_hub_abm.spatial.location import Location
from amr_hub_abm.spatial.room import Room


def test_route_uses_door_openings_and_rejects_disconnected_rooms() -> None:
    """A restaurant route uses doors and disappears if its source is disconnected."""
    rng = np.random.default_rng(42)
    space = SpaceInputReader(Path("tests/inputs/buildings.yml"), rng)
    staff = next(room for room in space.rooms if room.name == "Staff Room")
    restaurant = next(room for room in space.rooms if room.name == "Restaurant")
    chair = next(
        content
        for content in restaurant.contents
        if content.content_type == ContentType.CHAIR
    )
    agent = Agent(
        idx=1,
        location=Location(building="Sample Hospital", floor=0, x=4.5, y=0.5),
        heading_rad=0,
        rng_generator=rng,
    )
    route = route_to_facility(agent, staff, restaurant, chair.location, space.rooms)
    assert route is not None
    assert len(route) > 1
    assert route[-1] == chair.location

    staff.doors.clear()
    assert (
        route_to_facility(agent, staff, restaurant, chair.location, space.rooms) is None
    )


@pytest.fixture
def route_scenario() -> tuple[Agent, Room, Room, list[Room]]:
    """Create the synthetic staff-room-to-restaurant route."""
    rng = np.random.default_rng(42)
    space = SpaceInputReader(Path("tests/inputs/buildings.yml"), rng)
    staff = next(room for room in space.rooms if room.name == "Staff Room")
    restaurant = next(room for room in space.rooms if room.name == "Restaurant")
    agent = Agent(
        idx=1,
        location=Location(building="Sample Hospital", floor=0, x=4.5, y=0.5),
        heading_rad=0,
        rng_generator=rng,
    )
    return agent, staff, restaurant, space.rooms


def test_door_geometry_rejects_unusable_openings(
    route_scenario: tuple[Agent, Room, Room, list[Room]],
) -> None:
    """Topological, too-narrow and misplaced doors cannot yield route waypoints."""
    agent, staff, _, rooms = route_scenario
    door = staff.doors[0]
    corridor = next(room for room in rooms if room.room_id == 0)
    topological = replace(door, name="topological", start=None, end=None)
    narrow = replace(door, start=(3.0, 3.0), end=(3.01, 3.0))
    misplaced = replace(door, start=(100.0, 100.0), end=(101.0, 100.0))
    assert (
        _door_points(topological, staff, corridor, agent.interaction_radius, []) is None
    )
    assert _door_points(narrow, staff, corridor, agent.interaction_radius, []) is None
    assert (
        _door_points(misplaced, staff, corridor, agent.interaction_radius, []) is None
    )


def test_route_rejects_destination_on_another_floor(
    route_scenario: tuple[Agent, Room, Room, list[Room]],
) -> None:
    """A destination outside the source floor cannot be reached."""
    agent, staff, restaurant, rooms = route_scenario
    restaurant.floor = 1
    target = replace(restaurant.contents[0].location, floor=1)
    assert route_to_facility(agent, staff, restaurant, target, rooms) is None


def test_route_ignores_irrelevant_and_unusable_doors(
    route_scenario: tuple[Agent, Room, Room, list[Room]],
) -> None:
    """Disconnected and unusable openings are skipped instead of traversed."""
    agent, staff, restaurant, rooms = route_scenario
    door = staff.doors[0]
    staff.doors[:] = [
        replace(door, connecting_rooms=(8, 9), door_id=20),
        replace(door, name="missing geometry", start=None, end=None, door_id=21),
    ]
    assert (
        route_to_facility(
            agent, staff, restaurant, restaurant.contents[0].location, rooms
        )
        is None
    )


@pytest.mark.parametrize("blocked_segment", ["approach", "crossing"])
def test_route_skips_door_with_blocked_segment(
    route_scenario: tuple[Agent, Room, Room, list[Room]],
    monkeypatch: pytest.MonkeyPatch,
    blocked_segment: str,
) -> None:
    """An obstruction on either side of an opening prevents traversal."""
    agent, staff, restaurant, rooms = route_scenario
    target = restaurant.contents[0].location

    def clear_segment(
        start: Location, end: Location, _walls: object, _radius: float
    ) -> bool:
        if end == target:
            return False
        if start == agent.location:
            return blocked_segment == "crossing"
        return False

    monkeypatch.setattr(needs_navigation, "_clear_segment", clear_segment)
    assert route_to_facility(agent, staff, restaurant, target, rooms) is None
