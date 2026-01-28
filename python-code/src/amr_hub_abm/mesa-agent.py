"""Module to represent an agent in the AMR Hub ABM simulation."""
import math
from dataclasses import dataclass, field, replace
from enum import Enum
from logging import getLogger

import shapely
from matplotlib.axes import Axes
from mesa import Agent as MesaAgent  

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall
from amr_hub_abm.task import (
    Task,
    TaskPatientCare,
    TaskDoorAccess,
    TaskOfficeWork,
    TaskType,
    TaskProgress,
    TaskPriority
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
class Agent(MesaAgent):  # ← CHANGED: Inherit from MesaAgent
    """Representation of an agent in the AMR Hub ABM simulation."""

    unique_id: int  # 'idx'
    model: object   # Mesa requirement
    location: Location
    heading: float
    interaction_radius: float = field(default=0.05)
    tasks: list[Task] = field(default_factory=list)
    agent_type: AgentType = field(default=AgentType.GENERIC)
    infection_status: InfectionStatus = field(default=InfectionStatus.SUSCEPTIBLE)
    infection_details: dict = field(default_factory=dict)
    movement_speed: float = field(default=0.1)

    def __post_init__(self) -> None:
        """Post-initialization to log agent creation."""
        super().__init__(self.unique_id, self.model)  # ADDED: Call Mesa init
        self.heading = self.heading % 360

        logger.debug(
            "Created Agent id %s of type %s at location %s with heading %s",
            self.unique_id,  # ← CHANGED: Was self.idx
            self.agent_type,
            self.location,
            self.heading,
        )

    def step(self) -> None:  # ← ADDED: Mesa scheduler calls this
        """Execute one simulation step for this agent."""
        if hasattr(self.model, 'time') and hasattr(self.model, 'space_buildings'):
            current_time = self.model.time
            rooms = self.model.space_buildings
            self.perform_task(current_time, rooms)
        else:
            logger.warning(f"Agent {self.unique_id}: Model not properly initialized")

    # from previous version of agent.py
    
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
        msg = f"Moving Agent id {self.unique_id} from {self.location} to {new_location}"  # ← CHANGED
        logger.info(msg)
        self.location = new_location
        
        # update Mesa model space
        if hasattr(self.model, 'space') and self.model.space is not None:
            self.model.space.move_agent(self, (new_location.x, new_location.y))

    def plot_agent(self, ax: Axes, *, show_tags: bool = False) -> None:
        """Plot the agent on the given axes-- Modified from Mesa tutorials"""
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
                f"{self.agent_type.value} {self.unique_id}",  # ← CHANGED
                fontsize=8,
                ha="left",
                va="bottom",
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
            raise SimulationModeError(msg)
        task_type = TaskType(event_type)

        task: Task

        if task_type == TaskType.PATIENT_CARE:
            if additional_info is None or "patient" not in additional_info:
                msg = "Patient ID must be provided for attend_patient tasks."
                raise SimulationModeError(msg)

            patient = additional_info["patient"]
            if not isinstance(patient, Agent):
                msg = "Patient must be an instance of Agent."
                raise SimulationModeError(msg)

            task = TaskPatientCare(
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

        elif task_type == TaskType.OFFICE_WORK:
            task = TaskOfficework(
                office_location=location,
                time_needed=30,
                time_due=time,
            )

        else:
            msg = f"Task type {task_type} not implemented yet."
            raise NotImplementedError(msg)

        self.tasks.append(task)
