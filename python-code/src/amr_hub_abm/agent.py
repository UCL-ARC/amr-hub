"""Module to represent an agent in the AMR Hub ABM simulation."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from enum import IntEnum
from logging import getLogger
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.space.content import ContentType
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.task import (
    Task,
    TaskAttendPatient,
    TaskDoorAccess,
    TaskOccupyContent,
    TaskProgress,
    TaskType,
    TaskWorkstation,
)

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from numpy.random import Generator

    from amr_hub_abm.space.building import Building


TASK_TYPES = [task_type.name.lower() for task_type in TaskType]


logger = getLogger(__name__)


class AgentType(IntEnum):
    """Enumeration of possible agent types."""

    GENERIC = 0
    PATIENT = 1
    HEALTHCARE_WORKER = 2


ROLE_COLOUR_MAP = {
    AgentType.GENERIC: "blue",
    AgentType.PATIENT: "red",
    AgentType.HEALTHCARE_WORKER: "green",
}


class InfectionStatus(IntEnum):
    """Enumeration of possible infection statuses."""

    SUSCEPTIBLE = 0
    EXPOSED = 1
    INFECTED = 2
    RECOVERED = 3


@dataclass(slots=True)
class Record:
    """Representation of a record of an agent's state at a given time step."""

    total_time: int

    building: npt.NDArray[np.int8] = field(init=False)
    floor: npt.NDArray[np.int8] = field(init=False)
    position: npt.NDArray[np.float64] = field(init=False)
    heading: npt.NDArray[np.float64] = field(init=False)
    infection_status: npt.NDArray[np.int8] = field(init=False)

    def __post_init__(self) -> None:
        """Post-initialization to setup the record arrays."""
        self.building = np.empty(self.total_time, dtype=np.int8)
        self.floor = np.empty(self.total_time, dtype=np.int8)
        self.position = np.empty((self.total_time, 2), dtype=np.float64)
        self.heading = np.empty((self.total_time, 1), dtype=np.float64)
        self.infection_status = np.empty(self.total_time, dtype=np.int8)

    def push(  # noqa: PLR0913
        self,
        time: int,
        building_idx: int,
        floor: int,
        pos_x: float,
        pos_y: float,
        heading: float,
        infection_status: InfectionStatus,
    ) -> None:
        """Push a new record of the agent's state at a given time step."""
        if time >= self.total_time:
            msg = f"Time {time} exceeds total_time {self.total_time} for record."
            raise ValueError(msg)

        self.building[time] = building_idx
        self.floor[time] = floor
        self.heading[time] = heading
        self.position[time] = [pos_x, pos_y]
        self.infection_status[time] = infection_status.value


@dataclass
class Agent:
    """Representation of an agent in the AMR Hub ABM simulation."""

    idx: int
    location: Location
    heading_rad: float
    space: list[Building]
    rng_generator: Generator

    interaction_radius: float = field(default=0.01)
    tasks: list[Task] = field(default_factory=list)
    agent_type: AgentType = field(default=AgentType.GENERIC)
    infection_status: InfectionStatus = field(default=InfectionStatus.SUSCEPTIBLE)
    infection_details: dict = field(default_factory=dict)

    movement_speed: float = field(default=0.1)  # units per time step

    trajectory_length: int = field(default=0)
    trajectory: Record = field(init=False)

    stationary: bool = field(default=False, init=False)

    @property
    def heading_degrees(self) -> float:
        """Get the agent's heading in degrees."""
        return math.degrees(self.heading_rad)

    @heading_degrees.setter
    def heading_degrees(self, value: float) -> None:
        self.heading_rad = math.radians(value) % (2 * math.pi)

    def __post_init__(self) -> None:
        """Post-initialization to log agent creation."""
        # Ensure heading is between 0 and 360 degrees
        self.heading_rad = self.heading_rad % (2 * math.pi)

        logger.debug(
            "Created Agent id %s of type %s at location %s with heading %s",
            self.idx,
            self.agent_type,
            self.location,
            self.heading_rad,
        )

        if self.trajectory_length < 0:
            msg = "trajectory_length must be non-negative."
            raise ValueError(msg)

        if self.trajectory_length > 0:
            self.trajectory = Record(total_time=self.trajectory_length)

    def get_room(self, coords: tuple[float, float] | None = None) -> Room | None:
        """Get the room the agent is currently located in, if any."""
        if coords is None:
            coords = (self.location.x, self.location.y)

        for building in self.space:
            if building.name != self.location.building:
                continue
            for floor in building.floors:
                if floor.floor_number != self.location.floor:
                    continue
                room = floor.find_room_by_location(coords)
                if room:
                    return room
        logger.info(
            "Agent id %s is not located in any room. Location: %s",
            self.idx,
            self.location,
        )
        return None

    def check_if_location_reached(self, target_location: Location) -> bool:
        """Check if the agent has reached the target location."""
        if self.location.building != target_location.building:
            return False
        if self.location.floor != target_location.floor:
            return False

        distance = self.location.distance_to(target_location)
        return distance <= self.interaction_radius

    def move_to_location(self, new_location: Location) -> None:
        """Move the agent to a new location and log the movement."""
        msg = f"Moving Agent id {self.idx} from {self.location} to {new_location}"
        logger.info(msg)
        self.location = new_location

    def plot_agent(self, ax: Axes, *, show_tags: bool = True) -> None:
        """Plot the agent on the given axes."""
        ax.plot(
            self.location.x,
            self.location.y,
            marker="o",
            markersize=5,
            color=ROLE_COLOUR_MAP[self.agent_type],
        )

        if show_tags:
            ax.text(
                self.location.x + 0.05,
                self.location.y + 0.05,
                f"{self.agent_type.value} {self.idx}",
                fontsize=8,
                ha="left",
                va="bottom",
            )

    def plot_trajectory(self, ax: Axes) -> None:
        """Plot the agent's trajectory on the given axes."""
        if self.trajectory_length == 0:
            msg = "Cannot plot trajectory for agent with trajectory_length of 0."
            raise ValueError(msg)

        ax.plot(
            self.trajectory.position[:, 0],
            self.trajectory.position[:, 1],
            linestyle="-",
            linewidth=1.5,
            color=ROLE_COLOUR_MAP[self.agent_type],
            alpha=0.7,
        )

    def __repr__(self) -> str:
        """Return a string representation of the agent."""
        return (
            f"Agent(idx={self.idx}, {self.location}, "
            f"{math.degrees(self.heading_rad):.2f}°, "
            f"{self.interaction_radius}, {self.agent_type.value}, "
            f"{self.infection_status.value})"
        )

    def add_task(  # noqa: PLR0912
        self,
        time: int,
        location: Location,
        event_type: str,
        additional_info: dict | None = None,
    ) -> None:
        """Add a task to the agent's task list and log the addition."""
        if event_type not in TASK_TYPES:
            msg = f"Invalid task type: {event_type}. Must be one of {TASK_TYPES}."
            raise SimulationModeError(msg)
        task_type = TaskType[event_type.upper()]
        task: Task

        if task_type == TaskType.ATTEND_PATIENT:
            if additional_info is None or "patient" not in additional_info:
                msg = "Patient ID must be provided for attend_patient tasks."
                raise SimulationModeError(msg)

            patient = additional_info["patient"]
            if not isinstance(patient, Agent):
                msg = "Patient must be an instance of Agent."
                raise SimulationModeError(msg)

            task = TaskAttendPatient(
                time_needed=15,
                time_due=time,
                patient=patient,
            )

        elif task_type == TaskType.DOOR_ACCESS:
            if location.building is None or location.floor is None:
                msg = "Building and floor must be provided for door access tasks."
                raise SimulationModeError(msg)

            if (
                additional_info is None
                or "door" not in additional_info
                or not isinstance(additional_info["door"], Door)
            ):
                msg = "Door must be provided in additional_info for door access tasks."
                raise SimulationModeError(msg)

            task = TaskDoorAccess(
                door=additional_info["door"],
                destination_room=additional_info["destination"],
                time_needed=1,
                time_due=time,
                building=location.building,
                floor=location.floor,
            )

        elif task_type == TaskType.WORKSTATION:
            task = TaskWorkstation(
                workstation_location=location,
                time_needed=30,
                time_due=time,
            )

        elif task_type == TaskType.OCCUPY_CONTENT:
            if not additional_info or not isinstance(additional_info, dict):
                msg = "additional_info must be a dictionary for occupy_content tasks."
                raise SimulationModeError(msg)

            if "content_type" not in additional_info:
                msg = "Content type must be provided in additional_info for "
                msg += "occupy_content tasks."
                raise SimulationModeError(msg)

            if "room" not in additional_info or not isinstance(
                additional_info["room"], Room
            ):
                msg = (
                    "Room must be provided in additional_info for occupy_content tasks."
                )
                raise SimulationModeError(msg)

            task = TaskOccupyContent(
                content_type=additional_info["content_type"],
                room=additional_info["room"],
                time_needed=10,
                time_due=time,
            )

        else:
            msg = f"Task type {task_type.name} not implemented yet."
            raise NotImplementedError(msg)

        self.tasks.append(task)

    def head_to_point(self, point: tuple[float, float]) -> None:
        """Set the agent's heading to face a specific point."""
        delta_x = point[0] - self.location.x
        delta_y = point[1] - self.location.y

        self.heading_rad = math.atan2(delta_y, delta_x) % (2 * math.pi)

    @staticmethod
    def propose_new_coordinates(
        coordinates: tuple[float, float],
        heading_rad: float,
        movement_speed: float,
        stochasticity: float,
        rng_generator: Generator,
    ) -> tuple[float, float]:
        """Propose a new location for agent movement."""
        delta_x = movement_speed * math.cos(heading_rad)
        delta_y = movement_speed * math.sin(heading_rad)

        delta_x = (1 + rng_generator.normal(0, stochasticity)) * delta_x
        delta_y = (1 + rng_generator.normal(0, stochasticity)) * delta_y

        new_x = coordinates[0] + delta_x
        new_y = coordinates[1] + delta_y

        return new_x, new_y

    def try_move_one_step(
        self,
        stochasticity: float,
        max_attempts: int = 5,
    ) -> tuple[float, float]:
        """Return valid coordinates for a single movement step."""
        for attempt in range(1, max_attempts + 1):
            new_x, new_y = self.propose_new_coordinates(
                (self.location.x, self.location.y),
                self.heading_rad,
                self.movement_speed,
                stochasticity,
                self.rng_generator,
            )

            room = self.get_room((new_x, new_y))
            if room is None:
                logger.info(
                    "Attempt %s: location (%s, %s) is not located in any room.",
                    attempt,
                    new_x,
                    new_y,
                )
                continue

            walls = room.walls
            if not walls:
                msg = (
                    f"Room {room.name} has no walls defined, "
                    "cannot check for wall intersections."
                )
                raise SimulationModeError(msg)

            if Location.check_intersection_with_walls(
                new_x,
                new_y,
                self.interaction_radius,
                walls,
            ):
                logger.info(
                    "Attempt %s: Agent id %s cannot move to (%s, %s): "
                    "wall intersection.",
                    attempt,
                    self.idx,
                    new_x,
                    new_y,
                )
                continue

            return new_x, new_y

        logger.info(
            "Maximum attempts %s exceeded for moving one step. "
            "Agent id %s moving to proposed coordinates (%s, %s) despite "
            "wall intersection.",
            max_attempts,
            self.idx,
            self.location.x,
            self.location.y,
        )

        return new_x, new_y

    def move_one_step(self, stochasticity: float = 0.2) -> None:
        """Move the agent one step in the direction of its heading."""
        new_x, new_y = self.try_move_one_step(stochasticity)
        self.move_to_location(replace(self.location, x=new_x, y=new_y))

    def select_task_based_on_progress(
        self, progress: TaskProgress, *, allow_multiple: bool = False
    ) -> Task | None:
        """Select a task based on its progress."""
        tasks = [task for task in self.tasks if task.progress == progress]
        if not tasks:
            return None
        if len(tasks) > 1 and not allow_multiple:
            msg = f"Agent {self.idx} has multiple tasks"
            msg += f" with progress {progress.value}."
            logger.error(msg)
            raise RuntimeError(msg)
        return min(tasks, key=lambda t: (t.time_due, t.priority.value))

    def perform_in_progress_task(self, current_time: int) -> bool:
        """Perform an in-progress task and return True if a task was performed."""
        task = self.select_task_based_on_progress(TaskProgress.IN_PROGRESS)
        if task is None:
            return False
        task.update_progress(current_time=current_time, agent=self)
        return True

    def perform_moving_to_task_location(self, current_time: int) -> bool:
        """Move the agent towards the location of its next task."""
        next_task = self.select_task_based_on_progress(TaskProgress.MOVING_TO_LOCATION)
        if next_task is None:
            return False
        next_task.update_progress(current_time=current_time, agent=self)
        return True

    def perform_suspended_task(self, current_time: int) -> bool:
        """Perform a suspended task and return True if a task was performed."""
        task = self.select_task_based_on_progress(
            TaskProgress.SUSPENDED, allow_multiple=True
        )
        if task is None:
            return False
        task.update_progress(current_time=current_time, agent=self)
        return True

    def perform_to_be_started_task(self, current_time: int) -> bool:
        """Perform a to-be-started task and return True if a task was performed."""
        task = self.select_task_based_on_progress(
            TaskProgress.NOT_STARTED, allow_multiple=True
        )
        if task is None:
            return False
        if isinstance(task, TaskOccupyContent):
            task.assign_content()

        task_move_time = (
            task.time_due
            - task.time_needed
            - self.estimate_time_to_reach_location(task.location)
        )
        logger.info(
            "Agent id %s next task move time: %s, current time: %s",
            self.idx,
            task_move_time,
            current_time,
        )

        if current_time < task_move_time:
            self.attempt_task_insertion(
                next_task=task,
                next_task_move_time=task_move_time,
                current_time=current_time,
            )
            return False

        task.update_progress(current_time=current_time, agent=self)
        return True

    def record_state(self, current_time: int) -> None:
        """Push a record of the agent's current state to the trajectory."""
        if current_time >= self.trajectory_length:
            msg = f"Current time {current_time} "
            msg += f"exceeds trajectory length {self.trajectory_length}."
            raise ValueError(msg)

        building_idx_list = [
            b.idx for b in self.space if b.name == self.location.building
        ]
        if not building_idx_list:
            msg = f"Building {self.location.building} not found in agent's space."
            raise ValueError(msg)
        if len(building_idx_list) > 1:
            msg = f"Multiple buildings with name {self.location.building} found."
            raise ValueError(msg)
        building_idx = building_idx_list[0]

        self.trajectory.push(
            time=current_time,
            building_idx=building_idx,
            floor=self.location.floor,
            pos_x=self.location.x,
            pos_y=self.location.y,
            heading=self.heading_rad,
            infection_status=self.infection_status,
        )

    def perform_task(self, current_time: int, *, record: bool = False) -> None:
        """Perform the agent's current task if it's due."""
        if record:
            logger.info(
                "Recording state for Agent id %s at time %s: location=%s",
                self.idx,
                current_time,
                self.location,
            )
            self.record_state(current_time=current_time)

        if logger.isEnabledFor(logging.INFO):
            task_list_values = [task.task_type.value for task in self.tasks]
            task_progress_values = [task.progress.value for task in self.tasks]
            msg = f"Time {current_time} Task list: {task_list_values}"
            logger.info(msg)
            msg = f"Time {current_time} Task list: {task_progress_values}"
            logger.info(msg)

        if not self.tasks:
            return
        logger.debug(
            "Agent id %s has %s tasks to perform.",
            self.idx,
            len(self.tasks),
        )

        if self.perform_in_progress_task(current_time=current_time):
            return
        logger.debug(
            "No in-progress tasks for Agent id %s.",
            self.idx,
        )

        if self.perform_moving_to_task_location(current_time=current_time):
            return
        logger.debug(
            "No tasks to move to for Agent id %s.",
            self.idx,
        )

        if self.perform_suspended_task(current_time=current_time):
            return
        logger.debug(
            "No suspended tasks for Agent id %s.",
            self.idx,
        )

        if self.perform_to_be_started_task(current_time=current_time):
            return
        logger.debug(
            "No to-be-started tasks for Agent id %s.",
            self.idx,
        )

    def estimate_time_to_reach_location(self, target_location: Location) -> float:
        """Estimate the time required to reach a target location."""
        distance = self.location.distance_to(target_location)
        return distance / self.movement_speed

    def attempt_task_insertion(
        self, next_task: Task, next_task_move_time: float, current_time: int
    ) -> None:
        """Attempt to insert a task to occupy an empty chair."""
        if isinstance(next_task, TaskOccupyContent):
            return
        if self.stationary:
            return

        room = self.get_room()
        if room is None:
            logger.info(
                "Agent id %s is not located in any room. Cannot check for "
                "empty chairs for task %s.",
                self.idx,
                next_task.task_type.name,
            )
            return

        empty_chairs = [
            content
            for content in room.contents
            if content.content_type == ContentType.CHAIR and content.occupier_id is None
        ]

        logger.info(
            "Agent id %s found %s empty chairs in room %s for task %s.",
            self.idx,
            len(empty_chairs),
            room.name,
            next_task.task_type.name,
        )

        if empty_chairs:
            chair = empty_chairs[0]
            estimated_time_to_chair = self.estimate_time_to_reach_location(
                chair.location
            )
            if current_time + estimated_time_to_chair < next_task_move_time:
                self.add_task(
                    time=current_time,
                    location=chair.location,
                    event_type="occupy_content",
                    additional_info={
                        "content_type": ContentType.CHAIR,
                        "room": room,
                    },
                )
                logger.info(
                    """
                    Current time: %s
                    Estimated time to chair: %s
                    Next task move time: %s.
                    Agent id %s inserted occupy_content task for chair at location %s
                    to be performed before next task move time %s.
                    """,
                    current_time,
                    estimated_time_to_chair,
                    next_task_move_time,
                    self.idx,
                    chair.location,
                    next_task_move_time,
                )
                logger.warning(
                    """
                    Length of task list %s at time %s.
                    """,
                    len(self.tasks),
                    current_time,
                )
