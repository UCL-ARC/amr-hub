"""Module for collection of TaskBuilder functions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

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
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.spatial.door import Door
    from amr_hub_abm.spatial.furniture import ContentType
    from amr_hub_abm.spatial.location import Location
    from amr_hub_abm.spatial.room import Room

type TaskBuilder = Callable[[TaskBuilderContext], Task]


@dataclass(slots=True, frozen=True)
class TaskBuilderContext:
    """Context for building tasks."""

    time: int
    time_needed: int
    location: Location | None
    patient: Agent | None
    door: Door | None
    destination_room_idx: int | None
    content_type: ContentType | None
    content_room: Room | None


def build_task_context(
    time: int,
    time_needed: int,
    location: Location | None,
    additional_info: dict[str, object] | None = None,
) -> TaskBuilderContext:
    """
    Build a TaskBuilderContext from the legacy additional_info dict.

    This adapter can be removed once callers pass TaskBuilderContext directly.
    """
    additional_info = additional_info or {}

    return TaskBuilderContext(
        time=time,
        time_needed=time_needed,
        location=location,
        patient=cast("Agent | None", additional_info.get("patient")),
        door=cast("Door | None", additional_info.get("door")),
        destination_room_idx=cast("int | None", additional_info.get("destination")),
        content_type=cast("ContentType | None", additional_info.get("content_type")),
        content_room=cast("Room | None", additional_info.get("room")),
    )


def build_attend_patient_task(context: TaskBuilderContext) -> Task:
    """Build a TaskAttendPatient task."""
    if context.patient is None:
        msg = "Patient must be provided for attend_patient tasks."
        raise SimulationModeError(msg)

    return TaskAttendPatient(
        time_needed=context.time_needed,
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
        time_needed=context.time_needed,
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
        time_needed=context.time_needed,
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
        time_needed=context.time_needed,
        time_due=context.time,
    )


TASK_BUILDERS: dict[TaskType, TaskBuilder] = {
    TaskType.ATTEND_PATIENT: build_attend_patient_task,
    TaskType.DOOR_ACCESS: build_door_access_task,
    TaskType.WORKSTATION: build_workstation_task,
    TaskType.OCCUPY_CONTENT: build_occupy_content_task,
}
