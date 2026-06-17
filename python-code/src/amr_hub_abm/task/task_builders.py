"""Module for collection of TaskBuilder functions."""

from collections.abc import Callable
from dataclasses import dataclass

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.space.location import Location
from amr_hub_abm.task.task import Task, TaskAttendPatient

type TaskBuilder = Callable[[TaskBuilderContext], Task]


@dataclass
class TaskBuilderContext:
    """Context for building tasks."""

    time: int
    location: Location | None
    patient: Agent | None


def build_attend_patient_task(context: TaskBuilderContext) -> Task:
    """Build a TaskAttendPatient task."""
    if context.patient is None:
        msg = "Patient must be provided for attend_patient tasks."
        raise SimulationModeError(msg)

    if not isinstance(context.patient, Agent):
        msg = "Patient must be an instance of Agent."
        raise SimulationModeError(msg)

    return TaskAttendPatient(
        time_needed=15,
        time_due=context.time,
        patient=context.patient,
    )
