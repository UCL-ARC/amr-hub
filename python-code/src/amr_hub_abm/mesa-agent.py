from dataclasses import dataclass, field
from enum import Enum
from mesa import Agent as MesaAgent
from matplotlib.axes import Axes
import shapely.geometry
import logging

logger = logging.getLogger(__name__)


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
class Agent(MesaAgent):
    """Agent class integrated with Mesa for multi-agent simulation."""
    
    # Mesa required attributes (passed as positional args)
    unique_id: int
    model: object  # Your Mesa model instance
    
    # Your custom attributes
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
        """Post-initialization for both Mesa and custom setup."""
        # Call Mesa's parent __init__
        super().__init__(self.unique_id, self.model)
        
        # Your custom initialization
        self.heading = self.heading % 360
        logger.debug(
            "Created Agent id %s of type %s at location %s with heading %s",
            self.unique_id,
            self.agent_type,
            self.location,
            self.heading,
        )
    
    def step(self) -> None:
        """Define agent behavior at each time step (called by Mesa scheduler)."""
        current_time = self.model.schedule.steps
        
        # Execute scheduled tasks
        for task in self.tasks[:]:  # Copy list to allow safe removal
            if task.time == current_time:
                self.move_to_location(task.location)
                self.tasks.remove(task)
        
    
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
    
    def get_current_room(self) -> Room | None:
        """Get the room the agent is currently in (uses model's buildings)."""
        if hasattr(self.model, 'buildings'):
            return self.get_room(self.model.buildings)
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
    
    def check_wall_collision(self) -> bool:
        """Check if agent collides with any walls (uses model's walls)."""
        if hasattr(self.model, 'walls'):
            return self.check_intersection_with_walls(self.model.walls)
        return False
    
    def move_to_location(self, new_location: Location) -> None:
        """Move the agent to a new location and log the movement."""
        msg = f"Moving Agent id {self.unique_id} from {self.location} to {new_location}"
        logger.info(msg)
        self.location = new_location
        
        # Update Mesa's space if using ContinuousSpace
        if hasattr(self.model, 'space'):
            self.model.space.move_agent(self, (new_location.x, new_location.y))
    
    def rotate_heading(self, angle: float) -> None:
        """Rotate the agent's heading by a given angle."""
        old_heading = self.heading
        self.heading = (self.heading + angle) % 360
        msg = (
            f"Rotated Agent id {self.unique_id} heading from {old_heading} to {self.heading}"
        )
        logger.info(msg)
    
    def add_task(self, time: int, location: Location, event_type: str) -> None:
        """Add a task to the agent's task list and log the addition."""
        task_types = [task_type.value for task_type in TaskType]
        if event_type not in task_types:
            msg = f"Invalid task type: {event_type}. Must be one of {task_types}."
            raise ValueError(msg)
        
        task = Task(time=time, location=location, event_type=event_type)
        self.tasks.append(task)
        self.data_location_time_series.append((time, location))
        
        logger.debug(
            f"Added task {event_type} to Agent id {self.unique_id} at time {time}"
        )