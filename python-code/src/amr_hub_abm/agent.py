"""Module to represent an agent in the AMR Hub ABM simulation."""

import math
from dataclasses import dataclass, field, replace
from enum import IntEnum
from logging import getLogger

import numpy as np
import numpy.typing as npt
import shapely
from matplotlib.axes import Axes

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall
from amr_hub_abm.task import (
    Task,
    TaskAttendPatient,
    TaskDoorAccess,
    TaskProgress,
    TaskType,
    TaskWorkstation,
)

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

    position: npt.NDArray[np.float64] = field(init=False)
    heading: npt.NDArray[np.float64] = field(init=False)
    infection_status: npt.NDArray[np.int8] = field(init=False)

    def __post_init__(self) -> None:
        """Post-initialization to set up the record arrays."""
        self.position = np.empty((self.total_time, 2), dtype=np.float64)
        self.heading = np.empty((self.total_time, 1), dtype=np.float64)
        self.infection_status = np.empty(self.total_time, dtype=np.int8)

    def push(
        self,
        time: int,
        location: Location,
        heading: float,
        infection_status: InfectionStatus,
    ) -> None:
        """Push a new record of the agent's state at a given time step."""
        if time >= self.total_time:
            msg = f"Time {time} exceeds total_time {self.total_time} for record."
            raise ValueError(msg)

        self.heading[time] = heading
        self.position[time] = [location.x, location.y]
        self.infection_status[time] = infection_status.value


@dataclass
class Agent:
    """Representation of an agent in the AMR Hub ABM simulation."""

    idx: int
    location: Location
    heading: float
    interaction_radius: float = field(default=0.05)
    tasks: list[Task] = field(default_factory=list)
    agent_type: AgentType = field(default=AgentType.GENERIC)
    infection_status: InfectionStatus = field(default=InfectionStatus.SUSCEPTIBLE)
    infection_details: dict = field(default_factory=dict)

    movement_speed: float = field(default=0.1)  # units per time step

    trajectory_length: int = field(default=0)
    trajectory: Record = field(init=False)

    def __post_init__(self) -> None:
        """Post-initialization to log agent creation."""
        self.heading = self.heading % 360

        logger.debug(
            "Created Agent id %s of type %s at location %s with heading %s",
            self.idx,
            self.agent_type,
            self.location,
            self.heading,
        )

        if self.trajectory_length < 0:
            msg = "trajectory_length must be non-negative."
            raise ValueError(msg)

        if self.trajectory_length > 0:
            self.trajectory = Record(total_time=self.trajectory_length)

    def get_room(self, space: list[Building]) -> Room | None:
        """Get the room the agent is currently located in, if any."""
        for building in space:
            if building.name != self.location.building:
                continue
            for floor in building.floors:
                if floor.floor_number != self.location.floor:
                    continue
                room = floor.find_room_by_location((self.location.x, self.location.y))
                if room:
                    return room
        return None

    def check_intersection_with_walls(self, walls: list[Wall]) -> bool:
        """Check if the agent intersects with any walls."""
        for wall in walls:
            if (
                wall.polygon.distance(
                    shapely.geometry.Point(self.location.x, self.location.y)
                )
                < self.interaction_radius
            ):
                return True
        return False

    def check_if_location_reached(self, target_location: Location) -> bool:
        """Check if the agent has reached the target location."""
        if self.location.building != target_location.building:
            return False
        if self.location.floor != target_location.floor:
            return False

        distance = math.sqrt(
            (self.location.x - target_location.x) ** 2
            + (self.location.y - target_location.y) ** 2
        )
        return distance <= self.interaction_radius

    def move_to_location(self, new_location: Location) -> None:
        """Move the agent to a new location and log the movement."""
        msg = f"Moving Agent id {self.idx} from {self.location} to {new_location}"
        logger.info(msg)
        self.location = new_location

    def plot_agent(self, ax: Axes, *, show_tags: bool = False) -> None:
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

    def __repr__(self) -> str:
        """Return a string representation of the agent."""
        return (
            f"Agent(idx={self.idx}, {self.location}, {self.heading}, "
            f"{self.interaction_radius}, {self.agent_type.value}, "
            f"{self.infection_status.value})"
        )

    def add_task(
        self,
        time: int,
        location: Location,
        event_type: str,
        additional_info: dict | None = None,
    ) -> None:
        """Add a task to the agent's task list and log the addition."""
        task_types = [task_type.name.lower() for task_type in TaskType]
        if event_type not in task_types:
            msg = f"Invalid task type: {event_type}. Must be one of {task_types}."
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

        else:
            msg = f"Task type {task_type.name} not implemented yet."
            raise NotImplementedError(msg)

        self.tasks.append(task)

    def head_to_point(self, point: tuple[float, float]) -> None:
        """Set the agent's heading to face a specific point."""
        delta_x = point[0] - self.location.x
        delta_y = point[1] - self.location.y

        angle_radians = math.atan2(delta_y, delta_x)
        angle_degrees = math.degrees(angle_radians)

        self.heading = angle_degrees % 360

    def move_one_step(self) -> None:
        """Move the agent one step in the direction of its heading."""
        angle_radians = math.radians(self.heading)

        delta_x = self.movement_speed * math.cos(angle_radians)
        delta_y = self.movement_speed * math.sin(angle_radians)

        new_x = self.location.x + delta_x
        new_y = self.location.y + delta_y

        new_location = replace(
            self.location,
            x=new_x,
            y=new_y,
        )

        self.move_to_location(new_location)

    def perform_in_progress_task(self, current_time: int) -> bool:
        """Perform an in-progress task and return True if a task was performed."""
        in_progress_tasks = [
            task for task in self.tasks if task.progress == TaskProgress.IN_PROGRESS
        ]

        if not in_progress_tasks:
            return False

        if len(in_progress_tasks) > 1:
            msg = f"Agent id {self.idx} has multiple ongoing tasks."
            logger.error(msg)
            raise RuntimeError(msg)

        task = in_progress_tasks[0]
        task.update_progress(current_time=current_time, agent=self)
        return True

    def perform_moving_to_task_location(self, current_time: int) -> bool:
        """Move the agent towards the location of its next task."""
        moving_to_location_tasks = [
            task
            for task in self.tasks
            if task.progress == TaskProgress.MOVING_TO_LOCATION
        ]

        if not moving_to_location_tasks:
            return False

        if len(moving_to_location_tasks) > 1:
            msg = f"Agent id {self.idx} has multiple tasks to start."
            logger.error(msg)
            raise RuntimeError(msg)

        next_task = moving_to_location_tasks[0]
        next_task.update_progress(current_time=current_time, agent=self)
        return True

    def perform_suspended_task(self, current_time: int) -> bool:
        """Perform a suspended task and return True if a task was performed."""
        suspended_tasks = [
            task for task in self.tasks if task.progress == TaskProgress.SUSPENDED
        ]

        if not suspended_tasks:
            return False

        suspended_tasks.sort(key=lambda t: t.priority.value, reverse=True)
        task = suspended_tasks[0]
        task.update_progress(current_time=current_time, agent=self)
        return True

    def perform_to_be_started_task(self, current_time: int) -> bool:
        """Perform a to-be-started task and return True if a task was performed."""
        to_be_started_tasks = [
            task for task in self.tasks if task.progress == TaskProgress.NOT_STARTED
        ]

        if not to_be_started_tasks:
            return False

        to_be_started_tasks.sort(key=lambda t: t.priority.value, reverse=True)
        task = to_be_started_tasks[0]

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
            return False

        task.update_progress(current_time=current_time, agent=self)
        return True

    def record_state(self, current_time: int) -> None:
        """Push a record of the agent's current state to the trajectory."""
        if current_time >= self.trajectory_length:
            msg = f"Current time {current_time} "
            msg += f"exceeds trajectory length {self.trajectory_length}."
            raise ValueError(msg)

        self.trajectory.push(
            time=current_time,
            location=self.location,
            heading=self.heading,
            infection_status=self.infection_status,
        )

    def perform_task(
        self, current_time: int, rooms: list[Room], *, record: bool = False
    ) -> None:
        """Perform the agent's current task if it's due."""
        if record:
            logger.info(
                "Recording state for Agent id %s at time %s: location=%s",
                self.idx,
                current_time,
                self.location,
            )
            self.record_state(current_time=current_time)

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

        logger.debug(
            "Number of rooms available for Agent id %s: %s",
            self.idx,
            len(rooms),
        )

    def estimate_time_to_reach_location(self, target_location: Location) -> float:
        """Estimate the time required to reach a target location."""
        distance = self.location.distance_to(target_location)
        return distance / self.movement_speed
