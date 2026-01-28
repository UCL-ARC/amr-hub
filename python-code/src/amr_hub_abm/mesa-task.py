"""Module for AMR Hub ABM tasks."""
from dataclasses import dataclass, field
from enum import Enum
from amr_hub_abm.exceptions import TimeError


class TaskProgress(Enum):
    """Enumeration of possible task progress states."""
    NOT_STARTED = "not_started"
    MOVING_TO_LOCATION = "moving_to_location"
    IN_PROGRESS = "in_progress"
    SUSPENDED = "suspended"
    COMPLETED = "completed"


class TaskType(Enum):
    """Enumeration of possible task types."""
    PATIENT_CARE = "patient_care"
    GENERIC = "generic"
    OFFICE_WORK = "office_work"
    NURSE_ROUND = "nurse_round"  
    GOTO_LOCATION = "goto_location"
    GOTO_AGENT = "goto_agent"
    ATTEND_BELL = "attend_bell"
    STAY_IN_BED = "stay_in_bed"
    STAY_IN_ROOM = "stay_in_room"
    INTERACT_WITH_AGENT = "interact_with_agent"



class TaskPriority(Enum):
    """Enumeration of possible task priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class Task:
    """Base task representation."""
    time_needed: int
    time_due: int
    progress: TaskProgress = field(default=TaskProgress.NOT_STARTED, init=False)
    priority: TaskPriority = field(default=TaskPriority.MEDIUM)
    task_type: TaskType = field(init=False)
    
    def __post_init__(self) -> None:
        if self.time_needed < 0:
            raise TimeError("Time needed cannot be negative.")


@dataclass
class TaskPatientCare(Task):
    """Task for attending to a patient."""
    patient: object  # Agent reference
    
    def __post_init__(self) -> None:
        super().__post_init__()
        self.task_type = TaskType.PATIENT_CARE


@dataclass
class TaskDoorAccess(Task):
    """Task for accessing a door."""
    door: object  # Door reference
    building: str
    floor: int
    
    def __post_init__(self) -> None:
        super().__post_init__()
        self.task_type = TaskType.DOOR_ACCESS


@dataclass
class TaskOfficeWork(Task):
    """Task for working at a workstation."""
    office_location: object  # Location reference
    
    def __post_init__(self) -> None:
        super().__post_init__()
        self.task_type = TaskType.OFFICE_WORK