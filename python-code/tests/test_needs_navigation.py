"""Tests for facility routing on the synthetic hospital floorplan."""

from pathlib import Path

import numpy as np

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.agent.needs_navigation import route_to_facility
from amr_hub_abm.read_space_input import SpaceInputReader
from amr_hub_abm.spatial.furniture import ContentType
from amr_hub_abm.spatial.location import Location


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
