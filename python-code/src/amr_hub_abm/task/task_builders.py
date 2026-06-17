"""Module for collection of TaskBuilder functions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.task.task import (
    Task,
    TaskAttendPatient,
    TaskDoorAccess,
    TaskOccupyContent,
    TaskType,
    TaskWorkstation,
)

if TYPE_CHECKING:
    from amr_hub_abm.space.content import ContentType
    from amr_hub_abm.space.door import Door
    from amr_hub_abm.space.location import Location
    from amr_hub_abm.space.room import Room

type TaskBuilder = Callable[[TaskBuilderContext], Task]


@dataclass
class TaskBuilderContext:
    """Context for building tasks."""

    time: int
    location: Location | None
    patient: Agent | None
    door: Door | None
    destination_room_idx: int | None
    content_type: ContentType | None
    content_room: Room | None


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


def build_door_access_task(context: TaskBuilderContext) -> Task:
    """Build a TaskDoorAccess task."""
    if context.location is None:
        msg = "Location must be provided for door access tasks."
        raise SimulationModeError(msg)

    if context.location.building is None or context.location.floor is None:
        msg = "Building and floor must be provided for door access tasks."
        raise SimulationModeError(msg)

    if context.door is None:
        msg = "Door must be provided in additional_info for door access tasks."
        raise SimulationModeError(msg)

    if context.destination_room_idx is None:
        msg = "Destination room index must be provided for door access tasks."
        raise SimulationModeError(msg)

    return TaskDoorAccess(
        door=context.door,
        destination_room=context.destination_room_idx,
        time_needed=1,
        time_due=context.time,
        building=context.location.building,
        floor=context.location.floor,
    )


def build_workstation_task(context: TaskBuilderContext) -> Task:
    """Build a TaskWorkstation task."""
    if context.location is None:
        msg = "Location must be provided for workstation tasks."
        raise SimulationModeError(msg)

    return TaskWorkstation(
        workstation_location=context.location,
        time_needed=30,
        time_due=context.time,
    )


def build_occupy_content_task(context: TaskBuilderContext) -> Task:
    """Build a TaskOccupyContent task."""
    if context.content_type is None:
        msg = "Content type must be provided for occupy content tasks."
        raise SimulationModeError(msg)

    if context.content_room is None:
        msg = "Content room must be provided for occupy content tasks."
        raise SimulationModeError(msg)

    return TaskOccupyContent(
        content_type=context.content_type,
        room=context.content_room,
        time_needed=10,
        time_due=context.time,
    )


TASK_BUILDERS: dict[TaskType, TaskBuilder] = {
    TaskType.ATTEND_PATIENT: build_attend_patient_task,
    TaskType.DOOR_ACCESS: build_door_access_task,
    TaskType.WORKSTATION: build_workstation_task,
    TaskType.OCCUPY_CONTENT: build_occupy_content_task,
}
