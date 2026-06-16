"""Module containing functions for managing tasks in the AMR Hub ABM framework."""

import logging

from amr_hub_abm.task.task import Task, TaskProgress

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

    Raises
    ------
        RuntimeError
            If multiple tasks with the same progress status are found and
            allow_multiple is False.

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
