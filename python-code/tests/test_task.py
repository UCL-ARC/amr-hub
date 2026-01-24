"""Module defining tests for the AMR Hub ABM task functionalities."""

import pytest

from amr_hub_abm.exceptions import SimulationModeError, TimeError
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.location import Location
from amr_hub_abm.task import (
    Task,
    TaskDoorAccess,
    TaskGotoLocation,
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
    goto_task = TaskGotoLocation(
        progress=TaskProgress.NOT_STARTED,
        priority=TaskPriority.HIGH,
        time_needed=15,
        time_due=30,
        destination_location=Location(building="A", floor=1, x=10.0, y=20.0),
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
        open=True,
        connecting_rooms=(1, 2),
        access_control=(True, True),
    )

    door_task = TaskDoorAccess(
        progress=TaskProgress.NOT_STARTED,
        priority=TaskPriority.MEDIUM,
        time_needed=10,
        time_due=20,
        door=door,
        building="Building A",
        floor=0,
    )

    assert door_task.task_type == TaskType.DOOR_ACCESS
    assert door_task.location.building == "Building A"
    assert door_task.location.floor == 0


def test_door_access_task_with_invalid_door_raises() -> None:
    """Test that a DoorAccess task with an invalid door raises an error."""
    door = Door(
        name="Back Door",
        start=None,
        end=None,
        open=False,
        connecting_rooms=(3, 4),
        access_control=(False, False),
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
        )

    assert "Door must have defined start and end points to set task location." in str(
        excinfo.value
    )
