"""Module defining tests for the AMR Hub ABM task functionalities."""

import pytest

from amr_hub_abm.exceptions import TimeError
from amr_hub_abm.task import (
    Task,
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
        location_id=42,
        time_due=30,
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
