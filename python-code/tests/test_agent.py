"""Tests for the agent module."""

import math
from dataclasses import replace
from unittest.mock import MagicMock

import numpy as np
import pytest

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.agent.enums import ROLE_COLOUR_MAP, AgentType, InfectionStatus
from amr_hub_abm.agent.plotter import plot_agent
from amr_hub_abm.exceptions import NonNegativeValueError, SimulationModeError
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall


@pytest.fixture
def correct_agent() -> Agent:
    """Create a sample Agent for testing."""
    return Agent(
        idx=1,
        agent_type=AgentType.PATIENT,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(x=0.0, y=0.0, floor=1, building="Hospital"),
        heading_rad=math.pi / 2,  # 90 degrees in radians
        rooms=[],
        rng_generator=np.random.default_rng(),
    )


def test_agent_creation(correct_agent: Agent) -> None:
    """Test the creation of an Agent instance."""
    expected_location = Location(x=0.0, y=0.0, floor=1, building="Hospital")
    expected_heading = 90.0

    assert correct_agent.idx == 1
    assert correct_agent.agent_type == AgentType.PATIENT
    assert correct_agent.infection_status == InfectionStatus.SUSCEPTIBLE
    assert correct_agent.location == expected_location
    assert correct_agent.heading_degrees == expected_heading

    expected_location = Location(
        x=0.0, y=0.0, floor=1, building=Building(name="Hospital", floors=[]).name
    )
    expected_heading = 90.0

    assert correct_agent.idx == 1
    assert correct_agent.agent_type == AgentType.PATIENT
    assert correct_agent.infection_status == InfectionStatus.SUSCEPTIBLE
    assert correct_agent.location == expected_location
    assert correct_agent.heading_degrees == expected_heading


def test_heading_modulo() -> None:
    """Test that the heading is correctly set within 0-360 degrees."""
    agent = Agent(
        idx=2,
        agent_type=AgentType.HEALTHCARE_WORKER,
        infection_status=InfectionStatus.INFECTED,
        location=Location(
            x=5.0, y=5.0, floor=2, building=Building(name="Hospital", floors=[]).name
        ),
        heading_rad=math.radians(
            450
        ),  # 450 degrees in radians, should wrap to 90 degrees
        rooms=[],
        rng_generator=np.random.default_rng(),
    )
    expected_heading = 90.0

    assert agent.heading_degrees == expected_heading


def test_agent_heading(correct_agent: Agent) -> None:
    """Test that the heading degrees are correctly calculated."""
    assert correct_agent.heading_degrees == 90.0

    correct_agent.heading_rad = math.radians(180)
    assert correct_agent.heading_degrees == 180.0

    correct_agent.heading_degrees = 270.0
    assert math.isclose(correct_agent.heading_rad, math.radians(270), rel_tol=1e-9)


def test_agent_negative_trajectory_length() -> None:
    """Test that a negative trajectory length raises a NonNegativeValueError."""
    with pytest.raises(NonNegativeValueError) as exc_info:
        Agent(
            idx=3,
            agent_type=AgentType.GENERIC,
            infection_status=InfectionStatus.RECOVERED,
            location=Location(x=1.0, y=1.0, floor=1, building="Hospital"),
            heading_rad=0.0,
            rooms=[],
            rng_generator=np.random.default_rng(),
            trajectory_length=-5,  # Invalid negative trajectory length
        )

    assert "trajectory_length must be non-negative." in str(exc_info.value)


def test_head_to_point(correct_agent: Agent) -> None:
    """Test that the agent correctly heads towards a specified point."""
    target_x, target_y = 1.0, 1.0
    correct_agent.head_to_point((target_x, target_y))

    expected_heading_rad = math.atan2(
        target_y - correct_agent.location.y, target_x - correct_agent.location.x
    )
    assert math.isclose(correct_agent.heading_rad, expected_heading_rad, rel_tol=1e-9)


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
        heading_rad=math.pi,  # 180 degrees in radians
        rooms=[],
        rng_generator=np.random.default_rng(),
    )

    agent_not_intersecting = Agent(
        idx=4,
        agent_type=AgentType.GENERIC,
        infection_status=InfectionStatus.RECOVERED,
        location=Location(x=15.0, y=5.0, floor=1, building="Hospital"),
        heading_rad=0.0,
        rooms=[],
        rng_generator=np.random.default_rng(),
    )

    assert (
        Location.check_intersection_with_walls(
            agent_intersecting.location.x,
            agent_intersecting.location.y,
            agent_intersecting.interaction_radius,
            walls,
        )
        is True
    )

    assert (
        Location.check_intersection_with_walls(
            agent_not_intersecting.location.x,
            agent_not_intersecting.location.y,
            agent_not_intersecting.interaction_radius,
            walls,
        )
        is False
    )


def test_move_to_location() -> None:
    """Test that move_to_location updates the agent's location."""
    initial_location = Location(x=1.0, y=1.0, floor=1, building="Hospital")
    new_location = Location(x=2.5, y=3.5, floor=1, building="Hospital")

    agent = Agent(
        idx=5,
        agent_type=AgentType.GENERIC,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=initial_location,
        heading_rad=math.pi / 4,
        rooms=[],
        rng_generator=np.random.default_rng(),
    )

    agent.move_to_location(new_location)

    assert agent.location == new_location
    assert agent.location is new_location


def test_plot_agent_without_tags() -> None:
    """Test plotting an agent without showing tags calls ax.plot once."""
    agent = Agent(
        idx=7,
        agent_type=AgentType.PATIENT,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(x=1.0, y=2.0, floor=1, building="Hospital"),
        heading_rad=0.0,
        rooms=[],
        rng_generator=np.random.default_rng(),
    )
    ax = MagicMock()

    plot_agent(agent=agent, ax=ax, show_tags=False)

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
        heading_rad=0.0,
        rooms=[],
        rng_generator=np.random.default_rng(),
    )
    ax = MagicMock()

    plot_agent(agent=agent, ax=ax, show_tags=True)

    assert ax.plot.call_count == 2

    ax.plot.assert_any_call(
        agent.location.x,
        agent.location.y,
        marker="o",
        markersize=12,
        markerfacecolor="none",
        markeredgecolor="gold",
        markeredgewidth=2,
        zorder=2,
    )

    ax.plot.assert_any_call(
        agent.location.x,
        agent.location.y,
        marker="o",
        markersize=5,
        color=ROLE_COLOUR_MAP[agent.agent_type],
    )
    ax.text.assert_called_once_with(
        agent.location.x + 0.1,
        agent.location.y + 0.05,
        "Healthcare Worker 8\n(exposed)",
        fontsize=7,
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
        heading_rad=math.pi / 4,  # 45 degrees in radians
        rooms=[],
        rng_generator=np.random.default_rng(),
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

    assert "Patient must be provided for attend_patient tasks." in str(exc_info.value)


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

    assert "Task type GENERIC not implemented yet." in str(exc_info.value)


@pytest.fixture
def large_room() -> Room:
    """Create a large room location for testing."""
    return Room(
        room_id=1,
        name="LargeRoom",
        floor=1,
        building="TestBuilding",
        contents=[],
        walls=[
            Wall(start=(0, 0), end=(0, 100)),
            Wall(start=(0, 100), end=(100, 100)),
            Wall(start=(100, 100), end=(100, 0)),
            Wall(start=(100, 0), end=(0, 0)),
        ],
        doors=[],
        rng_generator=np.random.default_rng(),
    )


@pytest.fixture
def small_room() -> Room:
    """Create a small room location for testing."""
    return Room(
        room_id=2,
        name="SmallRoom",
        floor=1,
        building="TestBuilding",
        contents=[],
        walls=[
            Wall(start=(0, 0), end=(0, 1)),
            Wall(start=(0, 1), end=(1, 1)),
            Wall(start=(1, 1), end=(1, 0)),
            Wall(start=(1, 0), end=(0, 0)),
        ],
        doors=[],
        rng_generator=np.random.default_rng(),
    )


def test_try_moving_one_step(
    sample_agent: Agent,
    large_room: Room,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that try_moving_one_step successfully moves the agent when inside a room."""
    sample_agent.location = Location(x=50.0, y=50.0, floor=1, building="TestBuilding")
    sample_agent.rooms = [large_room]

    def fake_propose_new_location(*args, **kwargs) -> tuple[float, float]:  # noqa: ANN002, ANN003, ARG001
        return (50.5, 50.5)  # A location inside the large room

    monkeypatch.setattr(
        "amr_hub_abm.agent.agent.propose_new_coordinates", fake_propose_new_location
    )

    with caplog.at_level("INFO"):
        sample_agent.try_move_one_step(0.1)

        assert not any(
            "not located in any room." in message for message in caplog.messages
        )


def test_try_moving_one_step_outside_room(
    sample_agent: Agent,
    small_room: Room,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that try_moving_one_step raises NotImplementedError when outside room."""
    sample_agent.location = Location(x=2.0, y=2.0, floor=1, building="TestBuilding")
    sample_agent.rooms = [small_room]

    def fake_propose_new_location(*args, **kwargs) -> tuple[float, float]:  # noqa: ANN002, ANN003, ARG001
        return (10, 10)  # A location outside the small room

    monkeypatch.setattr(
        "amr_hub_abm.agent.agent.propose_new_coordinates", fake_propose_new_location
    )

    with caplog.at_level("INFO"):
        sample_agent.try_move_one_step(0.1)

        assert any("not located in any room." in message for message in caplog.messages)


def test_movement_trial_with_wall_intersection(
    sample_agent: Agent,
    large_room: Room,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that try_moving_one_step logs a warning when movement intersects walls."""
    sample_agent.location = Location(x=25.0, y=25.0, floor=1, building="TestBuilding")
    sample_agent.interaction_radius = 5.0

    sample_agent.rooms = [large_room]

    def fake_propose_new_location(*args, **kwargs) -> tuple[float, float]:  # noqa: ANN002, ANN003, ARG001
        return (98, 98)  # A location that crosses the wall between the two rooms

    monkeypatch.setattr(
        "amr_hub_abm.agent.agent.propose_new_coordinates", fake_propose_new_location
    )

    with caplog.at_level("INFO"):
        sample_agent.try_move_one_step(0.1)

    assert any("wall intersection." in message for message in caplog.messages)


def test_move_agent(sample_agent: Agent, large_room: Room) -> None:
    """Test that move_agent updates the agent's location correctly."""
    sample_agent.location = Location(x=10.0, y=10.0, floor=1, building="TestBuilding")
    sample_agent.rooms = [large_room]
    sample_agent.move_one_step()
    assert sample_agent.location.x != 10.0 or sample_agent.location.y != 10.0
