"""Module for AMR Hub ABM tasks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, ClassVar

from amr_hub_abm.exceptions import SimulationModeError, TimeError
from amr_hub_abm.space.location import Location

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from amr_hub_abm.agent import Agent
    from amr_hub_abm.space.door import Door


class TaskProgress(IntEnum):
    """Enumeration of possible task progress states."""

    NOT_STARTED = 0
    MOVING_TO_LOCATION = 1
    SUSPENDED = 2
    IN_PROGRESS = 3
    COMPLETED = 4


class TaskType(IntEnum):
    """Enumeration of possible task types."""

    GENERIC = 0
    OFFICE_WORK = 1
    NURSE_ROUND = 2
    ATTEND_PATIENT = 3
    GOTO_LOCATION = 4
    GOTO_AGENT = 5
    ATTEND_BELL = 6
    STAY_IN_BED = 7
    STAY_IN_ROOM = 8
    INTERACT_WITH_AGENT = 9
    DOOR_ACCESS = 10
    WORKSTATION = 11


class TaskPriority(IntEnum):
    """Enumeration of possible task priority levels."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class Task:
    """Representation of a task assigned to an agent."""

    task_type: ClassVar[TaskType] = TaskType.GENERIC

    time_needed: int
    time_due: int

    progress: TaskProgress = field(default=TaskProgress.NOT_STARTED, kw_only=True)
    priority: TaskPriority = field(default=TaskPriority.MEDIUM, kw_only=True)

    location: Location = field(init=False)

    time_started: int = field(init=False)
    time_completed: int = field(init=False)

    def time_spent(self, current_time: int) -> int:
        """Calculate the time spent on the task so far."""
        if self.progress == TaskProgress.COMPLETED:
            return self.time_completed - self.time_started

        if self.progress == TaskProgress.IN_PROGRESS:
            return current_time - self.time_started

        return 0

    def __post_init__(self) -> None:
        """Post-initialization to validate task attributes."""
        if self.time_needed < 0:
            msg = "Time needed for a task cannot be negative."
            raise TimeError(msg)

        if self.time_due < 0:
            msg = "Time due for a task cannot be negative."
            raise TimeError(msg)

    def update_progress(self, current_time: int, agent: Agent) -> None:
        """Update the progress of the task based on time spent."""
        if self.progress == TaskProgress.COMPLETED:
            return

        time_spent = self.time_spent(current_time=current_time)

        if time_spent >= self.time_needed:
            self.progress = TaskProgress.COMPLETED
            self.time_completed = current_time
            return

        if self.progress == TaskProgress.IN_PROGRESS:
            logger.info(
                "Agent id %s performing task %s at location %s.",
                agent.idx,
                self.task_type,
                self.location,
            )
            return

        if not agent.check_if_location_reached(self.location):
            self.progress = TaskProgress.MOVING_TO_LOCATION
            logger.info(
                "Agent id %s moving to task location %s.", agent.idx, self.location
            )
            agent.head_to_point((self.location.x, self.location.y))
            agent.move_one_step()
            return

        if self.progress == TaskProgress.MOVING_TO_LOCATION:
            self.progress = TaskProgress.IN_PROGRESS
            self.time_started = current_time

    def __repr__(self) -> str:
        """Representation of the task."""
        return (
            f"Task(type={self.task_type}, priority={self.priority}, "
            f"progress={self.progress}, time_needed={self.time_needed}, "
            f"time_due={self.time_due})"
        )


@dataclass
class TaskGotoLocation(Task):
    """Representation of a 'goto location' task."""

    task_type: ClassVar[TaskType] = TaskType.GOTO_LOCATION
    destination_location: Location

    def __post_init__(self) -> None:
        """Post-initialization to set the task location."""
        super().__post_init__()
        self.location = self.destination_location


@dataclass
class TaskAttendPatient(Task):
    """Representation of an 'attend patient' task."""

    task_type: ClassVar[TaskType] = TaskType.ATTEND_PATIENT
    patient: Agent

    def __post_init__(self) -> None:
        """Post-initialization to set the task location."""
        super().__post_init__()
        self.location = self.patient.location


@dataclass
class TaskDoorAccess(Task):
    """Representation of a 'door access' task."""

    task_type: ClassVar[TaskType] = TaskType.DOOR_ACCESS
    door: Door
    building: str
    floor: int

    def __post_init__(self) -> None:
        """Post-initialization to set the task location."""
        super().__post_init__()

        if self.door.start is None or self.door.end is None:
            msg = "Door must have defined start and end points to set task location."
            raise SimulationModeError(msg)

        self.location = Location(
            building=self.building,
            floor=self.floor,
            x=(self.door.start[0] + self.door.end[0]) / 2,
            y=(self.door.start[1] + self.door.end[1]) / 2,
        )


@dataclass
class TaskWorkstation(Task):
    """Representation of a 'workstation' task."""

    task_type: ClassVar[TaskType] = TaskType.WORKSTATION
    workstation_location: Location

    def __post_init__(self) -> None:
        """Post-initialization to set the task location."""
        super().__post_init__()
        self.location = self.workstation_location
