"""Test suite for Agent class."""

import numpy as np
import pytest

from amr_hub_abm.agent.agent import Agent, AgentType
from amr_hub_abm.agent.enums import InfectionStatus
from amr_hub_abm.config import sim_config
from amr_hub_abm.exceptions import NonNegativeValueError, SimulationModeError
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.content import Content, ContentType
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.space import SpatialQuery
from amr_hub_abm.space.wall import Wall
from amr_hub_abm.task.task import (
    Task,
    TaskAttendPatient,
    TaskDoorAccess,
    TaskOccupyContent,
    TaskType,
    TaskWorkstation,
)


@pytest.fixture
def rng_generator() -> np.random.Generator:
    """Fixture providing a random number generator."""
    return np.random.default_rng(seed=42)


@pytest.fixture
def sample_room(rng_generator: np.random.Generator) -> Room:
    """Fixture to provide a test Room instance."""
    return Room(
        room_id=1,
        name="Room A",
        building="Test Building",
        floor=1,
        walls=[
            Wall((0, 0), (100, 0)),
            Wall((100, 0), (100, 100)),
            Wall((100, 100), (0, 100)),
            Wall((0, 100), (0, 0)),
        ],
        contents=[],
        doors=[],
        rng_generator=rng_generator,
    )


@pytest.fixture
def engine(sample_room: Room) -> SpatialQuery:
    """Fixture providing a SpatialQuery engine with one building/floor/room."""
    floor = Floor(floor_number=sample_room.floor, rooms=[sample_room])
    building = Building(name=sample_room.building, floors=[floor])
    return SpatialQuery(space=[building])


@pytest.fixture
def setup_agent(
    sample_room: Room,  # noqa: ARG001
    rng_generator: np.random.Generator,
) -> Agent:
    """Fixture to set up a basic agent for testing."""
    location = Location(building="Test Building", floor=1, x=5.0, y=5.0)
    return Agent(
        idx=1,
        location=location,
        heading_rad=0.0,
        agent_type=AgentType.HEALTHCARE_WORKER,
        trajectory_length=10,
        rng_generator=rng_generator,
        movement_speed=0.5,
        stochasticity=5.0,
    )


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


def test_agent_initialization(setup_agent: Agent) -> None:
    """Test standard initialization of the Agent class."""
    agent = setup_agent
    assert agent.idx == 1
    assert agent.location.x == 5.0
    assert agent.location.y == 5.0
    assert agent.heading_rad == 0.0
    assert agent.agent_type == AgentType.HEALTHCARE_WORKER
    assert agent.infection_status == InfectionStatus.SUSCEPTIBLE
    assert agent.trajectory_length == 10
    assert agent.movement_speed == 0.5
    assert agent.stochasticity == 5.0


def test_invalid_trajectory_length(rng_generator: np.random.Generator) -> None:
    """Test that a negative trajectory length raises an error."""
    with pytest.raises(
        NonNegativeValueError, match="trajectory_length must be non-negative"
    ):
        Agent(
            idx=1,
            location=Location(building="Test Building", floor=1, x=5.0, y=5.0),
            heading_rad=0.0,
            trajectory_length=-1,
            rng_generator=rng_generator,
        )


# ---------------------------------------------------------------------------
# Task addition tests
# ---------------------------------------------------------------------------


def test_add_workstation_task(setup_agent: Agent) -> None:
    """Test adding a 'workstation' task to the agent."""
    agent = setup_agent
    location = Location(building="Test Building", floor=1, x=15.0, y=15.0)
    agent.add_task(
        time=0,
        location=location,
        event_type="workstation",
        time_needed=sim_config.task_durations.time_needed_workstation,
    )

    assert len(agent.tasks) == 1
    task = agent.tasks[0]
    assert isinstance(task, TaskWorkstation)
    assert task.workstation_location == location


def test_add_attend_patient_task(
    setup_agent: Agent, rng_generator: np.random.Generator
) -> None:
    """Test adding an 'attend_patient' task to the agent."""
    agent = setup_agent
    patient_location = Location(building="Test Building", floor=1, x=15.0, y=15.0)
    patient = Agent(
        idx=2,
        location=patient_location,
        heading_rad=0.0,
        agent_type=AgentType.PATIENT,
        rng_generator=rng_generator,
    )

    agent.add_task(
        time=0,
        location=patient_location,
        event_type="attend_patient",
        time_needed=sim_config.task_durations.time_needed_attend_patient,
        additional_info={"patient": patient},
    )

    assert len(agent.tasks) == 1
    task = agent.tasks[0]
    assert isinstance(task, TaskAttendPatient)
    assert task.patient == patient


def test_add_door_access_task(setup_agent: Agent) -> None:
    """Test adding a 'door_access' task to the agent."""
    agent = setup_agent
    location = Location(building="Test Building", floor=1, x=15.0, y=15.0)
    door_mock = type("Door", (), {"start": (0, 0), "end": (1, 1)})()

    agent.add_task(
        time=0,
        location=location,
        event_type="door_access",
        time_needed=sim_config.task_durations.time_needed_door_access,
        additional_info={"door": door_mock, "destination": 2},
    )

    assert len(agent.tasks) == 1
    task = agent.tasks[0]
    assert isinstance(task, TaskDoorAccess)
    assert task.door == door_mock
    assert task.destination_room == 2


def test_add_invalid_task_type(setup_agent: Agent) -> None:
    """Test that an invalid task type raises an error."""
    agent = setup_agent
    location = Location(building="Test Building", floor=1, x=15.0, y=15.0)

    with pytest.raises(SimulationModeError, match="Invalid task type"):
        agent.add_task(
            time=0, location=location, event_type="invalid_task", time_needed=5
        )


# ---------------------------------------------------------------------------
# Task insertion tests
# ---------------------------------------------------------------------------


def test_attempt_task_insertion(
    setup_agent: Agent,
    sample_room: Room,
    engine: SpatialQuery,
) -> None:
    """Test attempting task insertion for empty chair."""
    agent = setup_agent

    chair_location = Location(building="Test Building", floor=1, x=8.0, y=8.0)
    chair_content = Content(
        content_type=ContentType.CHAIR, location=chair_location, occupier_id=None
    )
    sample_room.contents.append(chair_content)

    next_task = Task(
        time_needed=sim_config.task_durations.time_needed_occupy_content,
        time_due=20,
        location=Location(building="Test Building", floor=1, x=10.0, y=10.0),
        task_type=TaskType.GOTO_LOCATION,
    )

    agent.attempt_task_insertion(
        next_task=next_task,
        next_task_move_time=15,
        current_time=0,
        engine=engine,
        task_durations=sim_config.task_durations,
    )

    assert len(agent.tasks) == 1
    task = agent.tasks[0]
    assert task.task_type.name == "OCCUPY_CONTENT"


def test_task_insertion_stationary_agent(
    setup_agent: Agent,
    engine: SpatialQuery,
) -> None:
    """Test that stationary agents do not get tasks inserted."""
    agent = setup_agent
    next_task = Task(
        time_needed=10,
        time_due=20,
        location=Location(building="Test Building", floor=1, x=10.0, y=10.0),
        task_type=TaskType.GOTO_LOCATION,
    )
    agent.tasks = [next_task]
    agent.stationary = True
    agent.attempt_task_insertion(
        next_task=next_task,
        next_task_move_time=5,
        current_time=5,
        engine=engine,
        task_durations=sim_config.task_durations,
    )
    assert len(agent.tasks) == 1


def test_task_insertion_existing_occupy_task(
    setup_agent: Agent,
    sample_room: Room,
    engine: SpatialQuery,
) -> None:
    """Test that occupy content tasks do not trigger further insertion."""
    agent = setup_agent
    occupy_task = TaskOccupyContent(
        time_due=5,
        time_needed=sim_config.task_durations.time_needed_occupy_content,
        content_type=ContentType.CHAIR,
        room=sample_room,
    )
    agent.tasks = [occupy_task]
    agent.attempt_task_insertion(
        next_task=occupy_task,
        next_task_move_time=5,
        current_time=5,
        engine=engine,
        task_durations=sim_config.task_durations,
    )
    assert len(agent.tasks) == 1


def test_task_insertion_invalid_location(
    setup_agent: Agent,
    engine: SpatialQuery,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that insertion is skipped when agent is not in any room."""
    agent = setup_agent
    agent.location = Location(x=0.0, y=0.0, floor=10, building="Test Building")
    next_task = Task(
        time_needed=1,
        time_due=20,
        location=Location(building="Test Building", floor=1, x=10.0, y=10.0),
        task_type=TaskType.GOTO_LOCATION,
    )
    agent.tasks = [next_task]

    with caplog.at_level("INFO"):
        agent.attempt_task_insertion(
            next_task=next_task,
            next_task_move_time=5,
            current_time=5,
            engine=engine,
            task_durations=sim_config.task_durations,
        )
        assert any("not located in any room" in message for message in caplog.messages)
    assert len(agent.tasks) == 1
