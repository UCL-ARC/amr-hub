"""Module to represent an agent in the AMR Hub ABM simulation."""

from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger

import shapely

from amr_hub_abm.space.building import Building
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall
from amr_hub_abm.task import Task

logger = getLogger(__name__)


class AgentType(Enum):
    """Enumeration of possible agent types."""

    GENERIC = "generic"
    PATIENT = "patient"
    HEALTHCARE_WORKER = "healthcare_worker"


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
        default_factory=list, init=False, repr=False
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
