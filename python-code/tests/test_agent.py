"""Tests for the agent module."""

from amr_hub_abm.agent import Agent, AgentType, InfectionStatus
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.wall import Wall


def test_agent_creation() -> None:
    """Test the creation of an Agent instance."""
    agent = Agent(
        idx=1,
        agent_type=AgentType.PATIENT,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(
            x=0.0, y=0.0, floor=1, building=Building(name="Hospital", floors=[]).name
        ),
        heading=90.0,
    )

    expected_location = Location(
        x=0.0, y=0.0, floor=1, building=Building(name="Hospital", floors=[]).name
    )
    expected_heading = 90.0

    assert agent.idx == 1
    assert agent.agent_type == AgentType.PATIENT
    assert agent.infection_status == InfectionStatus.SUSCEPTIBLE
    assert agent.location == expected_location
    assert agent.heading == expected_heading


def test_heading_modulo() -> None:
    """Test that the heading is correctly set within 0-360 degrees."""
    agent = Agent(
        idx=2,
        agent_type=AgentType.HEALTHCARE_WORKER,
        infection_status=InfectionStatus.INFECTED,
        location=Location(
            x=5.0, y=5.0, floor=2, building=Building(name="Hospital", floors=[]).name
        ),
        heading=450.0,  # 450 degrees should wrap to 90 degrees
    )
    expected_heading = 90.0

    assert agent.heading == expected_heading


def test_agent_intersection_with_walls() -> None:
    """Test if the agent correctly detects intersection with walls."""
    walls = [
        Wall(start=(0, 0), end=(0, 10)),
        Wall(start=(0, 10), end=(10, 10)),
        Wall(start=(10, 10), end=(10, 0)),
        Wall(start=(10, 0), end=(0, 0)),
    ]

    agent_intersecting = Agent(
        idx=3,
        agent_type=AgentType.HEALTHCARE_WORKER,
        infection_status=InfectionStatus.EXPOSED,
        location=Location(x=0.1, y=5.0, floor=1, building="Hospital"),
        heading=180.0,
    )

    agent_not_intersecting = Agent(
        idx=4,
        agent_type=AgentType.GENERIC,
        infection_status=InfectionStatus.RECOVERED,
        location=Location(x=15.0, y=5.0, floor=1, building="Hospital"),
        heading=0.0,
    )

    assert agent_intersecting.check_intersection_with_walls(walls) is True
    assert agent_not_intersecting.check_intersection_with_walls(walls) is False


def test_move_to_location() -> None:
    """Test that move_to_location updates the agent's location."""
    initial_location = Location(x=1.0, y=1.0, floor=1, building="Hospital")
    new_location = Location(x=2.5, y=3.5, floor=1, building="Hospital")

    agent = Agent(
        idx=5,
        agent_type=AgentType.GENERIC,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=initial_location,
        heading=45.0,
    )

    agent.move_to_location(new_location)

    assert agent.location == new_location
    assert agent.location is new_location


def test_rotate_heading() -> None:
    """Test that rotate_heading rotates and wraps the heading correctly."""
    agent = Agent(
        idx=6,
        agent_type=AgentType.GENERIC,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(x=0.0, y=0.0, floor=1, building="Hospital"),
        heading=350.0,
    )

    agent.rotate_heading(20.0)
    assert agent.heading == 10.0  # pylint: disable=literal-comparison

    agent.rotate_heading(-30.0)
    assert agent.heading == 340.0
