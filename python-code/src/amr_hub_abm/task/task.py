"""
Module for AMR Hub ABM tasks.

Design notes
------------
- ``Task`` is a plain dataclass with an explicit ``location`` field. Subclasses
  exist only where there is genuine behaviour (door buffering, content lookup),
  not just to set a location.
- Subclass-specific behaviour is expressed through lifecycle hooks
  (``on_start_moving``, ``on_started``, ``on_completed``) instead of
  ``isinstance`` checks in the base class.
- ``update_progress`` is a small explicit state machine: one handler per
  ``TaskProgress`` state.
- ``create_task`` is a factory that owns per-type defaults (durations etc.),
  so ``Agent.add_task`` no longer needs a long if/elif chain.
- The spatial engine (``SpatialQuery``) is threaded through as an explicit
  ``engine`` parameter rather than being accessed via the agent. This keeps
  the task layer decoupled from the agent's attributes and allows swapping
  CPU/GPU backends transparently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

from amr_hub_abm.agent.utils import add_agent_occupancy, remove_agent_occupancy
from amr_hub_abm.exceptions import SimulationModeError, TimeError
from amr_hub_abm.spatial.location import Location

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.spatial.door import Door
    from amr_hub_abm.spatial.engine import SpatialQuery
    from amr_hub_abm.spatial.furniture import Content
    from amr_hub_abm.spatial.room import Room


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


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
    OCCUPY_CONTENT = 12


class TaskPriority(IntEnum):
    """Enumeration of possible task priority levels."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


# ---------------------------------------------------------------------------
# Base task
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """
    Representation of a task assigned to an agent.

    A task is a small state machine driven by ``update_progress``. Subclasses
    customise behaviour via the lifecycle hooks ``prepare``,
    ``on_start_moving``, ``on_started`` and ``on_completed`` rather than by
    being special-cased in the base class.

    Parameters
    ----------
    time_needed : int
        The time required to complete the task.
    time_due : int
        The time by which the task should be completed.
    location : Location | None
        Where the task is performed. Simple task types (goto, workstation,
        attend patient) pass this directly; subclasses that derive their own
        location (door access, occupy content) may leave it None and set it
        in ``__post_init__`` / ``prepare``.
    progress : TaskProgress, optional
        Current progress. Defaults to NOT_STARTED.
    priority : TaskPriority, optional
        Priority level. Defaults to MEDIUM.

    """

    time_needed: int
    time_due: int
    location: Location | None = None

    task_type: TaskType = field(default=TaskType.GENERIC, kw_only=True)
    progress: TaskProgress = field(default=TaskProgress.NOT_STARTED, kw_only=True)
    priority: TaskPriority = field(default=TaskPriority.MEDIUM, kw_only=True)

    time_started: int | None = field(init=False, default=None)
    time_completed: int | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Validate timing attributes."""
        if self.time_needed < 0:
            msg = "Time needed for a task cannot be negative."
            raise TimeError(msg)
        if self.time_due < 0:
            msg = "Time due for a task cannot be negative."
            raise TimeError(msg)

    # -- lifecycle hooks (no-ops on the base class) -------------------------

    def prepare(self, agent: Agent) -> None:
        """
        Resolve any late-bound state before the task is first scheduled.

        Called once by the agent before the task leaves NOT_STARTED (e.g.
        ``TaskOccupyContent`` resolves which content to occupy here).
        """

    def on_start_moving(self, agent: Agent, engine: SpatialQuery) -> None:
        """Handle the transition to MOVING_TO_LOCATION."""

    def on_started(self, agent: Agent, current_time: int) -> None:
        """Handle the transition to IN_PROGRESS."""

    def on_completed(
        self, agent: Agent, current_time: int, engine: SpatialQuery
    ) -> None:
        """Handle the transition to COMPLETED."""

    # -- timing --------------------------------------------------------------

    def time_spent(self, current_time: int) -> int:
        """
        Calculate the time spent on the task so far.

        Raises
        ------
        TimeError
            If the task is COMPLETED or IN_PROGRESS but the corresponding
            timestamps are missing.

        """
        if self.progress == TaskProgress.COMPLETED:
            if self.time_started is None:
                msg = "Task marked as completed but start time is None."
                raise TimeError(msg)
            if self.time_completed is None:
                msg = "Task marked as completed but completion time is None."
                raise TimeError(msg)
            return self.time_completed - self.time_started

        if self.progress == TaskProgress.IN_PROGRESS:
            if self.time_started is None:
                msg = "Task marked as in progress but start time is None."
                raise TimeError(msg)
            return current_time - self.time_started

        return 0

    # -- state machine ---------------------------------------------------------

    def update_progress(
        self, current_time: int, agent: Agent, engine: SpatialQuery
    ) -> None:
        """
        Advance the task state machine by one tick.

        Dispatches to a handler per ``TaskProgress`` state. Completion is
        checked first since it can occur from any active state.
        """
        if self.progress == TaskProgress.COMPLETED:
            return

        if self.time_spent(current_time) >= self.time_needed:
            self._complete(current_time, agent, engine)
            return

        handler = {
            TaskProgress.IN_PROGRESS: self._tick_in_progress,
            TaskProgress.MOVING_TO_LOCATION: self._tick_moving,
            TaskProgress.NOT_STARTED: self._tick_not_started,
            TaskProgress.SUSPENDED: self._tick_not_started,
        }[self.progress]
        handler(current_time, agent, engine)

    def _complete(self, current_time: int, agent: Agent, engine: SpatialQuery) -> None:
        self.progress = TaskProgress.COMPLETED
        self.time_completed = current_time
        logger.info(
            "Task %s completed for Agent %s at t=%d.",
            self.task_type.name,
            agent.idx,
            current_time,
        )
        self.on_completed(agent, current_time, engine)

    def _tick_in_progress(
        self,
        current_time: int,  # noqa: ARG002
        agent: Agent,
        engine: SpatialQuery,  # noqa: ARG002
    ) -> None:
        logger.info(
            "Agent %s performing task %s at location %s.",
            agent.idx,
            self.task_type.name,
            self.location,
        )

    def _tick_moving(
        self, current_time: int, agent: Agent, engine: SpatialQuery
    ) -> None:
        if self.location is None:
            msg = f"Task {self.task_type.name} has no location to move to."
            raise SimulationModeError(msg)

        if engine.is_target_reached(
            agent.location, self.location, agent.interaction_radius
        ):
            self._start(current_time, agent)
            return

        engine.head_to_point(agent, (self.location.x, self.location.y))
        engine.move_one_step(agent)

    def _tick_not_started(
        self, current_time: int, agent: Agent, engine: SpatialQuery
    ) -> None:
        if self.location is None:
            msg = f"Task {self.task_type.name} has no location set."
            raise SimulationModeError(msg)

        if engine.is_target_reached(
            agent.location, self.location, agent.interaction_radius
        ):
            self._start(current_time, agent)
            return

        self.progress = TaskProgress.MOVING_TO_LOCATION
        self.on_start_moving(agent, engine)
        remove_agent_occupancy(agent, current_time=current_time, engine=engine)
        logger.info("Agent %s moving to task location %s.", agent.idx, self.location)
        engine.head_to_point(agent, (self.location.x, self.location.y))
        engine.move_one_step(agent)

    def _start(self, current_time: int, agent: Agent) -> None:
        self.progress = TaskProgress.IN_PROGRESS
        self.time_started = current_time
        self.on_started(agent, current_time)

    def __repr__(self) -> str:
        """Representation of the task."""
        return (
            f"{type(self).__name__}(type={self.task_type.name}, "
            f"priority={self.priority.name}, progress={self.progress.name}, "
            f"time_needed={self.time_needed}, time_due={self.time_due})"
        )


# ---------------------------------------------------------------------------
# Subclasses with real behaviour
# ---------------------------------------------------------------------------


@dataclass
class TaskAttendPatient(Task):
    """An 'attend patient' task. Carries the patient so the UI/agent can refer to it."""

    task_type: TaskType = field(default=TaskType.ATTEND_PATIENT, kw_only=True)
    patient: Agent | None = None

    def __post_init__(self) -> None:
        """Validate patient and set location."""
        super().__post_init__()
        if self.patient is None:
            msg = "TaskAttendPatient requires a patient."
            raise SimulationModeError(msg)
        self.location = self.patient.location


@dataclass
class TaskDoorAccess(Task):
    """A 'door access' task: position the agent just beyond the door midpoint."""

    task_type: TaskType = field(default=TaskType.DOOR_ACCESS, kw_only=True)
    door: Door | None = None
    building: str = ""
    floor: int = 0
    destination_room: int = -1
    buffer_distance: float = 0.05

    def __post_init__(self) -> None:
        """Validate door and compute midpoint location."""
        super().__post_init__()
        if self.door is None:
            msg = "TaskDoorAccess requires a door."
            raise SimulationModeError(msg)
        self.location = self._midpoint_location()

    def _midpoint(self) -> tuple[float, float]:
        assert self.door is not None  # noqa: S101 - validated in __post_init__
        if self.door.start is None or self.door.end is None:
            msg = "Door must have defined start and end points."
            raise SimulationModeError(msg)
        return (
            (self.door.start[0] + self.door.end[0]) / 2,
            (self.door.start[1] + self.door.end[1]) / 2,
        )

    def _midpoint_location(
        self, x_offset: float = 0.0, y_offset: float = 0.0
    ) -> Location:
        mid_x, mid_y = self._midpoint()
        return Location(
            building=self.building,
            floor=self.floor,
            x=mid_x + x_offset,
            y=mid_y + y_offset,
        )

    def on_start_moving(self, agent: Agent, engine: SpatialQuery) -> None:
        """Offset the target to the correct side of the door for the destination."""
        candidate = self._midpoint_location(
            x_offset=self.buffer_distance, y_offset=self.buffer_distance
        )
        candidate_room = engine.get_room(agent, coords=(candidate.x, candidate.y))
        if candidate_room is None:
            msg = "Proposed door-buffer location does not correspond to a valid room."
            raise SimulationModeError(msg)

        if candidate_room.room_id == self.destination_room:
            self.location = candidate
        else:
            self.location = self._midpoint_location(
                x_offset=-self.buffer_distance, y_offset=-self.buffer_distance
            )


@dataclass
class TaskOccupyContent(Task):
    """An 'occupy content' task: find matching content in a room and sit on it."""

    task_type: TaskType = field(default=TaskType.OCCUPY_CONTENT, kw_only=True)
    content_type: int = -1
    room: Room | None = None
    content: Content = field(init=False)

    def __post_init__(self) -> None:
        """Validate that a room is provided."""
        super().__post_init__()
        if self.room is None:
            msg = "TaskOccupyContent requires a room."
            raise SimulationModeError(msg)

    def prepare(self, agent: Agent) -> None:  # noqa: ARG002
        """Resolve the concrete content instance and set the task location."""
        assert self.room is not None  # noqa: S101 - validated in __post_init__
        content = next(
            (c for c in self.room.contents if c.content_type == self.content_type),
            None,
        )
        if content is None:
            msg = (
                f"No content of type {self.content_type} found in {self.room.name} "
                f"for 'occupy_content' task."
            )
            raise SimulationModeError(msg)

        self.content = content
        self.location = content.location

    def on_completed(
        self, agent: Agent, current_time: int, engine: SpatialQuery
    ) -> None:
        """Occupy the content once the task finishes."""
        add_agent_occupancy(
            agent, self.content, current_time=current_time, engine=engine
        )


@dataclass
class TaskWorkstation(Task):
    """A 'workstation' task: occupy a workstation in a room."""

    task_type: TaskType = field(default=TaskType.WORKSTATION, kw_only=True)
    workstation_location: Location | None = None

    def __post_init__(self) -> None:
        """Validate that a room is provided."""
        super().__post_init__()

    def prepare(self, agent: Agent) -> None:  # noqa: ARG002
        """Set the task location to the workstation location."""
        self.location = self.workstation_location


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

#: Default durations per task type, formerly hard-coded in Agent.add_task.
DEFAULT_TIME_NEEDED: dict[TaskType, int] = {
    TaskType.ATTEND_PATIENT: 15,
    TaskType.DOOR_ACCESS: 1,
    TaskType.WORKSTATION: 30,
    TaskType.OCCUPY_CONTENT: 10,
    TaskType.GOTO_LOCATION: 0,
}
