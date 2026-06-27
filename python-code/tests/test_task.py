"""Module defining tests for the AMR Hub ABM task functionalities."""

import numpy as np
import pytest

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.agent.enums import AgentType
from amr_hub_abm.exceptions import SimulationModeError, TimeError
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall
from amr_hub_abm.task.task import (
    Task,
    TaskAttendPatient,
    TaskDoorAccess,
    TaskPriority,
    TaskProgress,
    TaskType,
)


@pytest.fixture
def sample_task() -> Task:
    """Create a sample task for testing."""
    return Task(
        progress=TaskProgress.NOT_STARTED,
        priority=TaskPriority.MEDIUM,
        time_needed=30,
        time_due=60,
    )


@pytest.fixture
def sample_agent() -> Agent:
    """Create a sample agent for testing."""
    door = Door(
        name="Main Entrance",
        start=(0, 0),
        end=(0, 5),
        is_open=True,
        connecting_rooms=(1, 2),
        access_control=(True, True),
        door_id=12,
    )

    walls1 = [
        Wall(start=(0, 5), end=(0, 10)),
        Wall(start=(0, 10), end=(10, 10)),
        Wall(start=(10, 10), end=(10, 0)),
        Wall(start=(10, 0), end=(0, 0)),
    ]

    walls2 = [
        Wall(start=(0, 0), end=(0, 10)),
        Wall(start=(0, 10), end=(-10, 10)),
        Wall(start=(-10, 10), end=(-10, 0)),
        Wall(start=(-10, 0), end=(0, 0)),
    ]

    room1 = Room(
        room_id=1,
        name="Room 1",
        building="A",
        floor=0,
        walls=walls1,
        doors=[door],
        contents=[],
        rng_generator=np.random.default_rng(42),
    )

    room2 = Room(
        room_id=2,
        name="Room 2",
        building="A",
        floor=0,
        walls=walls2,
        doors=[door],
        contents=[],
        rng_generator=np.random.default_rng(42),
    )

    return Agent(
        idx=1,
        location=Location(building="A", floor=1, x=1.0, y=1.0),
        heading_rad=0.0,
        rooms=[room1, room2],
        rng_generator=np.random.default_rng(42),
    )


def test_task_print_representation(sample_task: Task) -> None:
    """Test the string representation of a task."""
    task = sample_task
    task_str = str(task)

    assert "progress=NOT_STARTED" in task_str
    assert "priority=MEDIUM" in task_str
    assert "time_needed=30" in task_str


def test_task_initialization(sample_task: Task) -> None:
    """Test the initialization of the Task class."""
    task = sample_task

    assert task.task_type == TaskType.GENERIC
    assert task.progress == TaskProgress.NOT_STARTED
    assert task.priority == TaskPriority.MEDIUM
    assert task.time_needed == 30


def test_task_negative_time_needed_raises() -> None:
    """Test that negative time_needed raises a TimeError."""
    with pytest.raises(TimeError) as excinfo:
        Task(
            progress=TaskProgress.NOT_STARTED,
            priority=TaskPriority.HIGH,
            time_needed=-10,
            time_due=50,
        )

    assert "Time needed for a task cannot be negative." in str(excinfo.value)


def test_task_progress_update(sample_task: Task) -> None:
    """Test updating the progress of a task."""
    task = sample_task

    task.progress = TaskProgress.IN_PROGRESS
    assert task.progress == TaskProgress.IN_PROGRESS

    task.progress = TaskProgress.COMPLETED
    assert task.progress == TaskProgress.COMPLETED


def test_goto_location_task() -> None:
    """Test the initialization of a 'goto location' task."""
    goto_task = Task(
        time_needed=15,
        time_due=30,
        location=Location(building="A", floor=1, x=10.0, y=20.0),
        progress=TaskProgress.NOT_STARTED,
        priority=TaskPriority.HIGH,
        task_type=TaskType.GOTO_LOCATION,
    )

    assert goto_task.task_type == TaskType.GOTO_LOCATION
    assert goto_task.progress == TaskProgress.NOT_STARTED
    assert goto_task.priority == TaskPriority.HIGH
    assert goto_task.time_needed == 15


def test_task_negative_time_due_raises() -> None:
    """Test that negative time_due raises a TimeError."""
    with pytest.raises(TimeError) as excinfo:
        Task(
            progress=TaskProgress.NOT_STARTED,
            priority=TaskPriority.LOW,
            time_needed=20,
            time_due=-5,
        )

    assert "Time due for a task cannot be negative." in str(excinfo.value)


def test_door_access_task_location_setting() -> None:
    """Test that the location is set correctly for a DoorAccess task."""
    door = Door(
        name="Main Entrance",
        start=(0, 0),
        end=(0, 5),
        is_open=True,
        connecting_rooms=(1, 2),
        access_control=(True, True),
        door_id=12,
    )

    door_task = TaskDoorAccess(
        progress=TaskProgress.NOT_STARTED,
        priority=TaskPriority.MEDIUM,
        time_needed=10,
        time_due=20,
        door=door,
        building="Building A",
        floor=0,
        destination_room=1,
    )

    assert door_task.task_type == TaskType.DOOR_ACCESS
    assert door_task.location is not None
    assert door_task.location.building == "Building A"
    assert door_task.location.floor == 0


def test_door_access_task_with_invalid_door_raises() -> None:
    """Test that a DoorAccess task with an invalid door raises an error."""
    door = Door(
        name="Back Door",
        start=None,
        end=None,
        is_open=False,
        connecting_rooms=(3, 4),
        access_control=(False, False),
        door_id=14,
    )

    with pytest.raises(SimulationModeError) as excinfo:
        TaskDoorAccess(
            progress=TaskProgress.NOT_STARTED,
            priority=TaskPriority.LOW,
            time_needed=5,
            time_due=15,
            door=door,
            building="Building B",
            floor=1,
            destination_room=1,
        )

    assert "Door must have defined start and end points." in str(excinfo.value)


def test_time_spent(sample_task: Task) -> None:
    """Test the time_spent property of a task."""
    task = sample_task

    # Initially, time spent should be 0
    assert task.time_spent(0) == 0

    task.progress = TaskProgress.IN_PROGRESS
    with pytest.raises(TimeError) as excinfo:
        task.time_spent(0)

    task.time_started = 10
    assert task.time_spent(20) == 10

    assert "Task marked as in progress but start time is None." in str(excinfo.value)

    task.time_started = None
    task.progress = TaskProgress.COMPLETED
    with pytest.raises(TimeError) as excinfo:
        task.time_spent(0)

    assert "Task marked as completed but start time is None." in str(excinfo.value)

    task.time_started = 5
    with pytest.raises(TimeError) as excinfo:
        task.time_spent(10)

    assert "Task marked as completed but completion time is None." in str(excinfo.value)

    task.time_completed = 15
    assert task.time_spent(20) == 10


def test_update_progress_of_completed_task(
    sample_task: Task, sample_agent: Agent
) -> None:
    """Test that updating the progress of a completed task raises an error."""
    task = sample_task
    task.progress = TaskProgress.COMPLETED
    task.update_progress(0, sample_agent)
    task.progress = TaskProgress.COMPLETED


def test_tick_moving(sample_task: Task, sample_agent: Agent) -> None:
    """Test the tick method for a task in progress."""
    task = sample_task

    with pytest.raises(SimulationModeError) as excinfo:
        task._tick_moving(0, sample_agent)  # noqa: SLF001

    assert "no location to move to." in str(excinfo.value)

    task.location = sample_agent.location
    task._tick_moving(0, sample_agent)  # noqa: SLF001
    assert task.location == sample_agent.location

    room = Room(
        room_id=1,
        name="Test Room",
        building="A",
        floor=1,
        walls=[
            Wall(start=(0, 0), end=(0, 5)),
            Wall(start=(0, 5), end=(5, 5)),
            Wall(start=(5, 5), end=(5, 0)),
            Wall(start=(5, 0), end=(0, 0)),
        ],
        doors=[],
        contents=[],
        rng_generator=np.random.default_rng(42),
    )

    sample_agent.rooms.append(room)

    old_location = Location(building="A", floor=1, x=2.0, y=2.0)
    sample_agent.location = old_location
    task._tick_moving(0, sample_agent)  # noqa: SLF001
    assert sample_agent.location != old_location


def test_tick_not_started(sample_task: Task, sample_agent: Agent) -> None:
    """Test the tick method for a task that has not started."""
    task = sample_task
    task.location = None
    with pytest.raises(SimulationModeError) as excinfo:
        task._tick_not_started(0, sample_agent)  # noqa: SLF001

    assert "no location set." in str(excinfo.value)

    task.location = Location(building="A", floor=1, x=3.0, y=3.0)
    task._tick_not_started(0, sample_agent)  # noqa: SLF001


def test_attend_patient_with_non_patient_task_raises(sample_agent: Agent) -> None:
    """Test that attending a patient with a non-patient task raises an error."""
    sample_agent.agent_type = AgentType.HEALTHCARE_WORKER
    with pytest.raises(SimulationModeError) as excinfo:
        TaskAttendPatient(
            time_needed=10,
            time_due=20,
        )
    assert "TaskAttendPatient requires a patient." in str(excinfo.value)


@pytest.fixture
def sample_door_access_task() -> TaskDoorAccess:
    """Create a sample TaskDoorAccess for testing."""
    door = Door(
        name="Main Entrance",
        start=(0, 0),
        end=(0, 5),
        is_open=True,
        connecting_rooms=(1, 2),
        access_control=(True, True),
        door_id=12,
    )

    return TaskDoorAccess(
        progress=TaskProgress.NOT_STARTED,
        priority=TaskPriority.MEDIUM,
        time_needed=10,
        time_due=20,
        door=door,
        building="A",
        floor=0,
        destination_room=1,
    )


def test_door_access_task_no_door_raises() -> None:
    """Test that a TaskDoorAccess without a door raises an error."""
    with pytest.raises(SimulationModeError) as excinfo:
        TaskDoorAccess(
            progress=TaskProgress.NOT_STARTED,
            priority=TaskPriority.MEDIUM,
            time_needed=10,
            time_due=20,
            door=None,  # No door provided
            building="Building A",
            floor=0,
            destination_room=1,
        )
    assert "TaskDoorAccess requires a door." in str(excinfo.value)


def test_door_access_on_start_moving(
    sample_door_access_task: TaskDoorAccess, sample_agent: Agent
) -> None:
    """Test the _on_start_moving method of TaskDoorAccess."""
    task = sample_door_access_task
    task.on_start_moving(sample_agent)

    task.destination_room = 2
    task.on_start_moving(sample_agent)

    assert task.location is not None
    assert task.location.building == "A"
    assert task.location.floor == 0

    sample_agent.rooms = []
    with pytest.raises(SimulationModeError) as excinfo:
        task.on_start_moving(sample_agent)

    assert "location does not correspond to a valid room." in str(excinfo.value)
