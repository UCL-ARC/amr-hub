"""Tests for the agent module."""

from amr_hub_abm.agent import Agent, AgentType, InfectionStatus
from amr_hub_abm.space.location import Building, Location


def test_agent_creation() -> None:
    """Test the creation of an Agent instance."""
    agent = Agent(
        idx=1,
        agent_type=AgentType.PATIENT,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(
            x=0.0, y=0.0, floor=1, building=Building(name="Hospital", floors=[])
        ),
        heading=90.0,
    )

    expected_location = Location(
        x=0.0, y=0.0, floor=1, building=Building(name="Hospital", floors=[])
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
            x=5.0, y=5.0, floor=2, building=Building(name="Hospital", floors=[])
        ),
        heading=450.0,  # 450 degrees should wrap to 90 degrees
    )
    expected_heading = 90.0

    assert agent.heading == expected_heading
