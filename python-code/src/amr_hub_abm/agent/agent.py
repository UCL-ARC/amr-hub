"""
Module to represent an agent in the AMR Hub ABM simulation.

This module defines the `Agent` class, which represents an individual agent in the
simulation. The `Agent` class includes attributes for the agent's location, heading,
tasks, and infection status, as well as methods for moving the agent, performing
tasks, and recording the agent's state over time. The module also defines related
classes and enumerations, such as `AgentType`, `InfectionStatus`, and `Record`, to
support the functionality of the `Agent` class.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from amr_hub_abm.agent.enums import AgentType, InfectionStatus
from amr_hub_abm.agent.output import Record, record_state
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.space.content import ContentType
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.space import (
    estimate_time_to_reach_location,
    get_room,
    propose_new_coordinates,
)
from amr_hub_abm.task.task import (
    Task,
    TaskAttendPatient,
    TaskDoorAccess,
    TaskOccupyContent,
    TaskType,
    TaskWorkstation,
)
from amr_hub_abm.task.tasklist import (
    perform_in_progress_task,
    perform_moving_to_task_location,
    perform_suspended_task,
    perform_to_be_started_task,
)

if TYPE_CHECKING:
    from numpy.random import Generator


TASK_TYPES = [task_type.name.lower() for task_type in TaskType]


logger = logging.getLogger(__name__)


# --8<--- [start:Agent]
@dataclass
class Agent:
    """Representation of an agent in the AMR Hub ABM simulation."""

    idx: int
    location: Location
    heading_rad: float
    rooms: list[Room]
    rng_generator: Generator

    interaction_radius: float = field(default=0.01)
    tasks: list[Task] = field(default_factory=list)
    agent_type: AgentType = field(default=AgentType.GENERIC)
    infection_status: InfectionStatus = field(default=InfectionStatus.SUSCEPTIBLE)
    infection_details: dict = field(default_factory=dict)

    movement_speed: float = field(default=0.001)  # units per time step
    stochasticity: float = field(default=5.0)  # degrees of randomness in movement

    trajectory_length: int = field(default=0)
    trajectory: Record = field(init=False)

    stationary: bool = field(default=False, init=False)

    # --8<--- [end:Agent]

    @property
    def heading_degrees(self) -> float:
        """
        Get the heading of the agent in degrees.

        Returns
        -------
        float
            Heading of the agent in degrees [0, 360).

        """
        return math.degrees(self.heading_rad)

    @heading_degrees.setter
    def heading_degrees(self, value: float) -> None:
        """
        Set the heading of the agent in degrees.

        Converts to radians and ensures it is between 0 and 360 degrees.

        Parameters
        ----------
        value : float
            The heading of the agent in degrees.

        """
        self.heading_rad = math.radians(value) % (2 * math.pi)

    def __post_init__(self) -> None:
        """
        Post-initialization to setup the trajectory record and validate parameters.

        Raises
        ------
        ValueError
            If the trajectory length is negative.

        """
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

    def move_to_location(self, new_location: Location) -> None:
        """
        Move the agent to a new location and log the movement.

        Parameters
        ----------
        new_location : Location
            The new location to which the agent will be moved.

        """
        msg = f"Moving Agent id {self.idx} from {self.location} to {new_location}"
        logger.info(msg)
        self.location = new_location

    def __repr__(self) -> str:
        """
        Return a string representation of the agent.

        Returns
        -------
        str
            A string representation of the agent, including its index, location,
            heading, interaction radius, type, and infection status.

        """
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
        """
        Add a task to the agent's task list and log the addition.

        Parameters
        ----------
        time : int
            The time at which the task is added.
        location : Location
            The location associated with the task.
        event_type : str
            The type of task to add. Must be one of the following:

            - "attend_patient"

            - "door_access"

            - "workstation"

            - "occupy_content"

        additional_info : dict | None, optional
            Additional information required for certain task types.

            For "attend_patient" tasks, this should include:

            - "patient": An instance of Agent representing the patient to attend.
            For "door_access" tasks, this should include:

            - "door": An instance of Door representing the door to access.

            - "destination": The rooom number of the destination room to which
            the agent will move after accessing the door.

            For "occupy_content" tasks, this should include:

            - "content_type": A ContentType representing the type of content to occupy.

            - "room": An instance of Room representing the room in which to occupy the
            content.

        Raises
        ------
            SimulationModeError
                If the event_type is invalid or if required additional_info is missing
                or of the wrong type for the specified event_type.

        """
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
        """
        Set the agent's heading to face a specific point.

        Parameters
        ----------
        point : tuple[float, float]
            The (x, y) coordinates of the point to face.

        """
        delta_x = point[0] - self.location.x
        delta_y = point[1] - self.location.y

        self.heading_rad = math.atan2(delta_y, delta_x) % (2 * math.pi)

    def try_move_one_step(
        self,
        stochasticity: float,
        max_attempts: int = 5,
    ) -> tuple[float, float]:
        """
        Return valid coordinates for a single movement step.

        Parameters
        ----------
        stochasticity : float
            The level of randomness to apply to the movement.
        max_attempts : int, optional
            The maximum number of attempts to find valid coordinates without wall
            intersection.

        Returns
        -------
        tuple[float, float]
            The proposed new (x, y) coordinates for the agent after moving one step.

        Raises
        ------
        SimulationModeError
            If the agent cannot find valid coordinates after the maximum number of
            attempts, or if the room has no walls defined for intersection checking.

        """
        for attempt in range(1, max_attempts + 1):
            new_x, new_y = propose_new_coordinates(
                (self.location.x, self.location.y),
                self.heading_rad,
                self.movement_speed,
                stochasticity,
                self.rng_generator,
            )

            new_location = Location(
                x=new_x,
                y=new_y,
                floor=self.location.floor,
                building=self.location.building,
            )
            room = get_room(new_location, self.rooms)
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

        logger.error(
            "Maximum attempts %s exceeded for moving one step. "
            "Agent id %s moving to proposed coordinates (%s, %s) despite "
            "wall intersection.",
            max_attempts,
            self.idx,
            self.location.x,
            self.location.y,
        )

        return self.location.x, self.location.y

    def move_one_step(self) -> None:
        """Move the agent one step in the direction of its heading."""
        new_x, new_y = self.try_move_one_step(self.stochasticity)
        self.move_to_location(replace(self.location, x=new_x, y=new_y))

    def perform_task(self, current_time: int, *, record: bool = False) -> None:
        """
        Perform the agent's current task if it's due.

        Parameters
        ----------
        current_time : int
            The current time step in the simulation.
        record : bool, optional
            Whether to record the agent's state at the current time step.

        """
        if record:
            logger.info(
                "Recording state for Agent id %s at time %s: location=%s",
                self.idx,
                current_time,
                self.location,
            )
            record_state(agent=self, current_time=current_time)

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

        if perform_in_progress_task(self, current_time=current_time):
            return
        logger.debug(
            "No in-progress tasks for Agent id %s.",
            self.idx,
        )

        if perform_moving_to_task_location(self, current_time=current_time):
            return
        logger.debug(
            "No tasks to move to for Agent id %s.",
            self.idx,
        )

        if perform_suspended_task(self, current_time=current_time):
            return
        logger.debug(
            "No suspended tasks for Agent id %s.",
            self.idx,
        )

        if perform_to_be_started_task(self, current_time=current_time):
            return
        logger.debug(
            "No to-be-started tasks for Agent id %s.",
            self.idx,
        )

    def attempt_task_insertion(
        self, next_task: Task, next_task_move_time: float, current_time: int
    ) -> None:
        """
        Attempt to insert a task to occupy an empty chair.

        This method checks if the next task is not already an occupy_content task and if
        the agent is not stationary. If these conditions are met, it checks for empty
        chairs in the current room and estimates the time to reach the chair. If the
        agent can reach the chair before the next task move time, it inserts an
        `occupy_content` task for the chair.

        Parameters
        ----------
        next_task : Task
            The next task for which to attempt insertion of an occupy_content task.
        next_task_move_time : float
            The time at which the next task is scheduled to move to the next stage.
        current_time : int
            The current time step in the simulation.

        """
        if isinstance(next_task, TaskOccupyContent):
            return
        if self.stationary:
            return

        room = get_room(self.location, self.rooms)
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
            estimated_time_to_chair = estimate_time_to_reach_location(
                self.location, chair.location, self.movement_speed
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
