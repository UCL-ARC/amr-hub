"""Tests for the agent module."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from amr_hub_abm.agent import ROLE_COLOUR_MAP, Agent, AgentType, InfectionStatus
from amr_hub_abm.exceptions import SimulationModeError
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


def test_plot_agent_without_tags() -> None:
    """Test plotting an agent without showing tags calls ax.plot once."""
    agent = Agent(
        idx=7,
        agent_type=AgentType.PATIENT,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(x=1.0, y=2.0, floor=1, building="Hospital"),
        heading=0.0,
    )
    ax = MagicMock()

    agent.plot_agent(ax=ax, show_tags=False)

    ax.plot.assert_called_once_with(
        agent.location.x,
        agent.location.y,
        marker="o",
        markersize=5,
        color=ROLE_COLOUR_MAP[agent.agent_type],
    )
    ax.text.assert_not_called()


def test_plot_agent_with_tags() -> None:
    """Test plotting an agent with tags also calls ax.text."""
    agent = Agent(
        idx=8,
        agent_type=AgentType.HEALTHCARE_WORKER,
        infection_status=InfectionStatus.EXPOSED,
        location=Location(x=0.5, y=0.25, floor=1, building="Hospital"),
        heading=0.0,
    )
    ax = MagicMock()

    agent.plot_agent(ax=ax, show_tags=True)

    ax.plot.assert_called_once_with(
        agent.location.x,
        agent.location.y,
        marker="o",
        markersize=5,
        color=ROLE_COLOUR_MAP[agent.agent_type],
    )
    ax.text.assert_called_once_with(
        agent.location.x + 0.05,
        agent.location.y + 0.05,
        f"{agent.agent_type.value} {agent.idx}",
        fontsize=8,
        ha="left",
        va="bottom",
    )


@pytest.fixture
def sample_location() -> Location:
    """Create a sample Location for testing."""
    return Location(
        x=10.0,
        y=20.0,
        floor=2,
        building="TestBuilding",
    )


@pytest.fixture
def sample_agent(sample_location: Location) -> Agent:
    """Create a sample Agent for testing."""
    return Agent(
        idx=10,
        agent_type=AgentType.HEALTHCARE_WORKER,
        infection_status=InfectionStatus.INFECTED,
        location=sample_location,
        heading=90.0,
    )


def test_invalid_event_type_in_add_task(
    sample_agent: Agent, sample_location: Location
) -> None:
    """Test that ValueError is raised for an invalid event type in add_task."""
    with pytest.raises(SimulationModeError) as exc_info:
        sample_agent.add_task(
            time=0,
            location=sample_location,
            event_type="invalid_event",
        )

    assert "Invalid task type" in str(exc_info.value)


def test_add_attend_patient_task_without_patient(
    sample_agent: Agent, sample_location: Location
) -> None:
    """Test that error is raised when adding attend_patient task without patient."""
    with pytest.raises(SimulationModeError) as exc_info:
        sample_agent.add_task(
            time=0,
            location=sample_location,
            event_type="attend_patient",
        )

    assert "Patient ID must be provided for attend_patient tasks." in str(
        exc_info.value
    )


def test_add_attend_patient_task_with_invalid_patient(
    sample_agent: Agent, sample_location: Location
) -> None:
    """Test that error is raised if adding task with invalid patient."""
    with pytest.raises(SimulationModeError) as exc_info:
        sample_agent.add_task(
            time=0,
            location=sample_location,
            event_type="attend_patient",
            additional_info={"patient": "not_an_agent"},
        )

    assert "Patient must be an instance of Agent." in str(exc_info.value)


def test_add_door_access_task_without_building_floor(
    sample_agent: Agent, sample_location: Location
) -> None:
    """Test that error is raised if adding task without building and floor."""
    incomplete_location = replace(sample_location, building=None, floor=None)  # type: ignore  # noqa: PGH003

    with pytest.raises(SimulationModeError) as exc_info:
        sample_agent.add_task(
            time=0,
            location=incomplete_location,
            event_type="door_access",
            additional_info={"door": MagicMock()},
        )

    assert "Building and floor must be provided for door access tasks." in str(
        exc_info.value
    )


def test_add_door_access_task_without_door(
    sample_agent: Agent, sample_location: Location
) -> None:
    """Test that SimulationModeError is raised when adding task without door info."""
    with pytest.raises(SimulationModeError) as exc_info:
        sample_agent.add_task(
            time=0,
            location=sample_location,
            event_type="door_access",
            additional_info={},
        )

    assert "Door must be provided in additional_info for door access tasks." in str(
        exc_info.value
    )


def test_add_task_with_not_implemented_task_type(
    sample_agent: Agent, sample_location: Location
) -> None:
    """Test that NotImplementedError is raised for unimplemented task types."""
    with pytest.raises(NotImplementedError) as exc_info:
        sample_agent.add_task(
            time=0,
            location=sample_location,
            event_type="generic",
        )

    assert "Task type TaskType.GENERIC not implemented yet." in str(exc_info.value)
