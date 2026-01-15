"""Module to represent an agent in the AMR Hub ABM simulation."""

from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger

import shapely
from matplotlib.axes import Axes

from amr_hub_abm.space.building import Building
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall
from amr_hub_abm.task import (
    Task,
    TaskAttendPatient,
    TaskDoorAccess,
    TaskType,
    TaskWorkstation,
)

logger = getLogger(__name__)


class AgentType(Enum):
    """Enumeration of possible agent types."""

    GENERIC = "generic"
    PATIENT = "patient"
    HEALTHCARE_WORKER = "healthcare_worker"


ROLE_COLOUR_MAP = {
    AgentType.GENERIC: "blue",
    AgentType.PATIENT: "red",
    AgentType.HEALTHCARE_WORKER: "green",
}


class InfectionStatus(Enum):
    """Enumeration of possible infection statuses."""

    SUSCEPTIBLE = "susceptible"
    EXPOSED = "exposed"
    INFECTED = "infected"
    RECOVERED = "recovered"


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

    data_location_time_series: list[tuple[int, Location]] = field(
        default_factory=list, init=False
    )

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

    def move_to_location(self, new_location: Location) -> None:
        """Move the agent to a new location and log the movement."""
        msg = f"Moving Agent id {self.idx} from {self.location} to {new_location}"
        logger.info(msg)
        self.location = new_location

    def rotate_heading(self, angle: float) -> None:
        """Rotate the agent's heading by a given angle."""
        old_heading = self.heading
        self.heading = (self.heading + angle) % 360
        msg = (
            f"Rotated Agent id {self.idx} heading from {old_heading} to {self.heading}"
        )
        logger.info(msg)

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
        task_types = [task_type.value for task_type in TaskType]
        if event_type not in task_types:
            msg = f"Invalid task type: {event_type}. Must be one of {task_types}."
            raise ValueError(msg)
        task_type = TaskType(event_type)

        task: Task

        if task_type == TaskType.ATTEND_PATIENT:
            if additional_info is None or "patient" not in additional_info:
                msg = "Patient ID must be provided for attend_patient tasks."
                raise ValueError(msg)

            patient = additional_info["patient"]
            if not isinstance(patient, Agent):
                msg = "Patient must be an instance of Agent."
                raise ValueError(msg)

            task = TaskAttendPatient(
                time_needed=15,
                time_due=time,
                patient=patient,
            )

        elif task_type == TaskType.DOOR_ACCESS:
            if location.building is None or location.floor is None:
                msg = "Building and floor must be provided for door access tasks."
                raise ValueError(msg)

            if (
                additional_info is None
                or "door" not in additional_info
                or not isinstance(additional_info["door"], Door)
            ):
                msg = "Door must be provided in additional_info for door access tasks."
                raise ValueError(msg)

            task = TaskDoorAccess(
                door=additional_info["door"],
                time_needed=0,
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
            msg = f"Task type {task_type} not implemented yet."
            raise NotImplementedError(msg)

        self.tasks.append(task)
