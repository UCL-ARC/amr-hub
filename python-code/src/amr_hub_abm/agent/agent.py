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
from typing import TYPE_CHECKING

import mesa

from amr_hub_abm.agent.enums import AgentType, InfectionStatus
from amr_hub_abm.agent.output import Record, record_state
from amr_hub_abm.exceptions import NonNegativeValueError, SimulationModeError
from amr_hub_abm.space.content import ContentType
from amr_hub_abm.task.task import (
    Task,
    TaskOccupyContent,
    TaskType,
)
from amr_hub_abm.task.task_builders import TASK_BUILDERS, build_task_context
from amr_hub_abm.task.tasklist import (
    perform_in_progress_task,
    perform_moving_to_task_location,
    perform_suspended_task,
    perform_to_be_started_task,
)

if TYPE_CHECKING:
    from numpy.random import Generator

    from amr_hub_abm.space.location import Location
    from amr_hub_abm.space.space import SpatialQuery


TASK_TYPES = [task_type.name.lower() for task_type in TaskType]

logger = logging.getLogger(__name__)


# --8<--- [start:Agent]
class Agent(mesa.Agent):
    """
    Representation of an agent in the AMR Hub ABM simulation.

    Subclasses ``mesa.Agent`` so the Mesa scheduler can call ``step()``.
    The ``model`` reference is set when the agent is added to the
    scheduler in ``Simulation.__init__``, so agents can be constructed
    before the model exists.

    Parameters
    ----------
    idx : int
        Unique identifier for the agent (also used as Mesa's unique_id).
    location : Location
        The initial location of the agent.
    heading_rad : float
        The initial heading of the agent in radians.
    rng_generator : Generator
        Random number generator for stochastic movement.
    interaction_radius : float, optional
        The radius within which the agent can interact, by default 0.01.
    agent_type : AgentType, optional
        The type of agent, by default GENERIC.
    trajectory_length : int, optional
        Number of time steps to record, by default 0 (no recording).
    movement_speed : float, optional
        Speed of the agent in units per time step, by default 0.001.
    stochasticity : float, optional
        Degrees of randomness in movement, by default 5.0.

    """

    def __init__(  # noqa: PLR0913
        self,
        idx: int,
        location: Location,
        heading_rad: float,
        rng_generator: Generator,
        interaction_radius: float = 0.01,
        tasks: list[Task] | None = None,
        agent_type: AgentType = AgentType.GENERIC,
        infection_status: InfectionStatus = InfectionStatus.SUSCEPTIBLE,
        infection_details: dict | None = None,
        movement_speed: float = 0.001,
        stochasticity: float = 5.0,
        trajectory_length: int = 0,
        *,
        use_gpu: bool = False,
    ) -> None:
        """Initialise an agent with its location, heading, and task list."""
        # Mesa requires unique_id and model. We pass a dummy model=None
        # here because agents are constructed in simulation_factory before
        # the Model exists. Simulation.__init__ sets the real model
        # reference when it calls self.schedule.add(agent).
        super().__init__(unique_id=idx, model=None)  # type: ignore[arg-type]

        self.idx = idx
        self.location = location
        self.heading_rad = heading_rad % (2 * math.pi)
        self.rng_generator = rng_generator

        self.interaction_radius = interaction_radius
        self.tasks: list[Task] = tasks if tasks is not None else []
        self.agent_type = agent_type
        self.infection_status = infection_status
        self.infection_details: dict = (
            infection_details if infection_details is not None else {}
        )

        self.movement_speed = movement_speed
        self.stochasticity = stochasticity
        self.trajectory_length = trajectory_length

        self.stationary: bool = False

        # GPU compatibility placeholders
        self.use_gpu = use_gpu
        self.target_x: float = 0.0
        self.target_y: float = 0.0

        logger.debug(
            "Created Agent id %s of type %s at location %s with heading %s",
            self.idx,
            self.agent_type,
            self.location,
            self.heading_rad,
        )

        if self.trajectory_length < 0:
            msg = "trajectory_length must be non-negative."
            raise NonNegativeValueError(msg)

        if self.trajectory_length > 0:
            self.trajectory = Record(total_time=self.trajectory_length)

    # --8<--- [end:Agent]
    # --------------------------------------------------------------------------
    # Mesa entry point
    # --------------------------------------------------------------------------

    def step(self) -> None:
        """Advance the agent by one tick via the Mesa scheduler."""
        self.perform_task(
            current_time=self.model.schedule.steps,
            engine=self.model.spatial_engine,
            record=getattr(self.model, "_record_this_step", False),
        )

    # --------------------------------------------------------------------------
    # Properties
    # --------------------------------------------------------------------------

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

    # --------------------------------------------------------------------------
    # String representation
    # --------------------------------------------------------------------------

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

    # --------------------------------------------------------------------------
    # Task management
    # --------------------------------------------------------------------------

    def add_task(
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
            The type of task to add.
        additional_info : dict | None, optional
            Additional information required for certain task types.

        Raises
        ------
            SimulationModeError
                If the event_type is invalid.

        """
        if event_type not in TASK_TYPES:
            msg = f"Invalid task type: {event_type}. Must be one of {TASK_TYPES}."
            raise SimulationModeError(msg)
        task_type = TaskType[event_type.upper()]
        if task_type == TaskType.GENERIC:
            msg = "Task type GENERIC not implemented yet."
            raise NotImplementedError(msg)

        context = build_task_context(
            time=time,
            location=location,
            additional_info=additional_info,
        )

        task = TASK_BUILDERS[task_type](context)
        self.tasks.append(task)

    def perform_task(
        self, current_time: int, engine: SpatialQuery, *, record: bool = False
    ) -> None:
        """
        Perform the agent's current task if it's due.

        Parameters
        ----------
        current_time : int
            The current time step in the simulation.
        engine : SpatialQuery
            The engine instance used to resolve geometry queries and bounds.
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

        if not self.tasks:
            return

        task_handlers = (
            perform_in_progress_task,
            perform_moving_to_task_location,
            perform_suspended_task,
            perform_to_be_started_task,
        )

        for handler in task_handlers:
            if handler(self, current_time=current_time, engine=engine):
                return

    def attempt_task_insertion(
        self,
        next_task: Task,
        next_task_move_time: float,
        current_time: int,
        engine: SpatialQuery,
    ) -> None:
        """
        Attempt to insert a task to occupy an empty chair.

        Parameters
        ----------
        next_task : Task
            The next task for which to attempt insertion of an
            occupy_content task.
        next_task_move_time : float
            The time at which the next task is scheduled to move to
            the next stage.
        current_time : int
            The current time step in the simulation.
        engine: SpatialQuery
            The SpatialQuery instance for resolving spatial queries.

        """
        if isinstance(next_task, TaskOccupyContent):
            return
        if self.stationary:
            return

        room = engine.get_room(self)
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
            estimated_time_to_chair = engine.estimate_time_to_reach_location(
                self, chair.location
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
                    "Current time: %s, Estimated time to chair: %s, "
                    "Next task move time: %s. Agent id %s inserted "
                    "occupy_content task for chair at location %s.",
                    current_time,
                    estimated_time_to_chair,
                    next_task_move_time,
                    self.idx,
                    chair.location,
                )
