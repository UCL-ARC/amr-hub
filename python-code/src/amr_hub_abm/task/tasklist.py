"""Module containing functions for managing tasks in the AMR Hub ABM framework."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from amr_hub_abm.config import sim_config
from amr_hub_abm.task.task import TaskProgress

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.space.space import SpatialQuery
    from amr_hub_abm.task.task import Task

logger = logging.getLogger(__name__)


def select_task_based_on_progress(
    tasklist: list[Task], progress: TaskProgress, *, allow_multiple: bool = False
) -> Task | None:
    """
    Select a task based on its progress.

    Parameters
    ----------
    tasklist : list[Task]
        The list of tasks to filter.
    progress : TaskProgress
        The progress status to filter tasks by.
    allow_multiple : bool, optional
        Whether to allow multiple tasks with the same progress status.

    Returns
    -------
    Task | None
        The selected task with the specified progress status, or None if no such
        task exists.

    """
    tasks = [task for task in tasklist if task.progress == progress]
    if not tasks:
        return None
    if len(tasks) > 1 and not allow_multiple:
        msg = "Agent has multiple tasks"
        msg += f" with progress {progress.value}."
        logger.error(msg)
        raise RuntimeError(msg)
    return min(tasks, key=lambda t: (t.time_due, t.priority.value))


def perform_in_progress_task(
    agent: Agent, current_time: int, engine: SpatialQuery
) -> bool:
    """Perform an in-progress task and return True if a task was performed."""
    task = select_task_based_on_progress(agent.tasks, TaskProgress.IN_PROGRESS)
    if task is None:
        return False
    task.update_progress(current_time=current_time, agent=agent, engine=engine)
    return True


def perform_moving_to_task_location(
    agent: Agent, current_time: int, engine: SpatialQuery
) -> bool:
    """Move the agent towards the location of its next task."""
    next_task = select_task_based_on_progress(
        agent.tasks, TaskProgress.MOVING_TO_LOCATION
    )
    if next_task is None:
        return False
    next_task.update_progress(current_time=current_time, agent=agent, engine=engine)
    return True


def perform_suspended_task(
    agent: Agent, current_time: int, engine: SpatialQuery
) -> bool:
    """Perform a suspended task and return True if a task was performed."""
    task = select_task_based_on_progress(
        agent.tasks, TaskProgress.SUSPENDED, allow_multiple=True
    )
    if task is None:
        return False
    task.update_progress(current_time=current_time, agent=agent, engine=engine)
    return True


def perform_to_be_started_task(
    agent: Agent, current_time: int, engine: SpatialQuery
) -> bool:
    """Perform a to-be-started task and return True if a task was performed."""
    task = select_task_based_on_progress(
        agent.tasks, TaskProgress.NOT_STARTED, allow_multiple=True
    )
    if task is None:
        return False
    task.prepare(agent=agent)
    assert task.location is not None  # noqa: S101

    # Engine handles estimating travel distances!
    task_move_time = (
        task.time_due
        - task.time_needed
        - engine.estimate_time_to_reach_location(agent, task.location)
    )
    logger.info(
        "Agent id %s next task move time: %s, current time: %s",
        agent.idx,
        task_move_time,
        current_time,
    )

    if current_time < task_move_time:
        task_durations = sim_config.task_durations

        agent.attempt_task_insertion(
            next_task=task,
            next_task_move_time=task_move_time,
            current_time=current_time,
            engine=engine,
            task_durations=task_durations,
        )
        return False

    task.update_progress(current_time=current_time, agent=agent, engine=engine)
    return True
