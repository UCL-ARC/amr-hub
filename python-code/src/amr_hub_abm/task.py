"""Module for AMR Hub ABM tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

from amr_hub_abm.exceptions import TimeError
from amr_hub_abm.space.location import Location

if TYPE_CHECKING:
    from amr_hub_abm.agent import Agent
    from amr_hub_abm.space.door import Door


class TaskProgress(Enum):
    """Enumeration of possible task progress states."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskType(Enum):
    """Enumeration of possible task types."""

    GENERIC = "generic"
    OFFICE_WORK = "office_work"
    NURSE_ROUND = "nurse_round"
    ATTEND_PATIENT = "attend_patient"
    GOTO_LOCATION = "goto_location"
    GOTO_AGENT = "goto_agent"
    ATTEND_BELL = "attend_bell"
    STAY_IN_BED = "stay_in_bed"
    STAY_IN_ROOM = "stay_in_room"
    INTERACT_WITH_AGENT = "interact_with_agent"
    DOOR_ACCESS = "door_access"
    WORKSTATION = "workstation"


class TaskPriority(Enum):
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

    def __post_init__(self) -> None:
        """Post-initialization to validate task attributes."""
        if self.time_needed < 0:
            msg = "Time needed for a task cannot be negative."
            raise TimeError(msg)

        if self.time_due < 0:
            msg = "Time due for a task cannot be negative."
            raise TimeError(msg)


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
            raise ValueError(msg)

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
