"""Module for AMR Hub ABM tasks."""

from dataclasses import dataclass, field
from enum import Enum

from amr_hub_abm.exceptions import TimeError


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

    task_type: TaskType = field(init=False)
    progress: TaskProgress
    priority: TaskPriority
    time_needed: int
    time_due: int

    def __post_init__(self) -> None:
        """Post-initialization to validate task attributes."""
        self.task_type = TaskType.GENERIC

        if self.time_needed < 0:
            msg = "Time needed for a task cannot be negative."
            raise TimeError(msg)

        if self.time_due < 0:
            msg = "Time due for a task cannot be negative."
            raise TimeError(msg)


@dataclass
class TaskGotoLocation(Task):
    """Representation of a 'goto location' task."""

    location_id: int

    def __post_init__(self) -> None:
        """Post-initialization to set task type."""
        super().__post_init__()
        self.task_type = TaskType.GOTO_LOCATION


@dataclass
class TaskAttendPatient(Task):
    """Representation of an 'attend patient' task."""

    patient_id: int

    def __post_init__(self) -> None:
        """Post-initialization to set task type."""
        super().__post_init__()
        self.task_type = TaskType.ATTEND_PATIENT


@dataclass
class TaskDoorAccess(Task):
    """Representation of a 'door access' task."""

    door_id: int

    def __post_init__(self) -> None:
        """Post-initialization to set task type."""
        super().__post_init__()
        self.task_type = TaskType.DOOR_ACCESS


@dataclass
class TaskWorkstation(Task):
    """Representation of a 'workstation' task."""

    room_id: int

    def __post_init__(self) -> None:
        """Post-initialization to set task type."""
        super().__post_init__()
        self.task_type = TaskType.WORKSTATION
