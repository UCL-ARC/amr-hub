"""Module containing functions related to agent output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent, InfectionStatus


@dataclass(slots=True)
class Record:
    """
    Representation of a record of an agent's state at a given time step.

    Parameters
    ----------
    total_time: int
        The total number of time steps for which to record the agent's state.

    """

    total_time: int

    building: npt.NDArray[np.int8] = field(init=False)
    floor: npt.NDArray[np.int8] = field(init=False)
    position: npt.NDArray[np.float64] = field(init=False)
    heading: npt.NDArray[np.float64] = field(init=False)
    infection_status: npt.NDArray[np.int8] = field(init=False)

    def __post_init__(self) -> None:
        """
        Simply initialises the numpy arrays of the class to be empty.

        This includes the building, floor, position, heading, and infection status.
        All of these are stored as integers and floats (and not strings) for memory
        efficiency
        """
        self.building = np.empty(self.total_time, dtype=np.int8)
        self.floor = np.empty(self.total_time, dtype=np.int8)
        self.position = np.full((self.total_time, 2), np.nan, dtype=np.float64)
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
        """
        Push a new record of the agent's state at a given time step.

        Parameters
        ----------
        time : int
            The time step for which to record the agent's state.
        building_idx : int
            The index of the building in which the agent is located.
        floor : int
            The floor number on which the agent is located.
        pos_x : float
            The x-coordinate of the agent's position.
        pos_y : float
            The y-coordinate of the agent's position.
        heading : float
            The heading of the agent in radians.
        infection_status : InfectionStatus
            The infection status of the agent.

        Raises
        ------
        ValueError
            If the time step exceeds the total_time for the record.

        """
        if time >= self.total_time:
            msg = f"Time {time} exceeds total_time {self.total_time} for record."
            raise ValueError(msg)

        self.building[time] = building_idx
        self.floor[time] = floor
        self.heading[time] = heading
        self.position[time] = [pos_x, pos_y]
        self.infection_status[time] = infection_status.value


def record_state(agent: Agent, current_time: int) -> None:
    """
    Push a record of the agent's current state to the trajectory.

    Parameters
    ----------
    current_time : int
        The current time step in the simulation for which to record the agent's
        state.

    Raises
    ------
        ValueError
            If the current_time exceeds the trajectory_length of the agent.

    """
    if current_time >= agent.trajectory_length:
        msg = f"Current time {current_time} "
        msg += f"exceeds trajectory length {agent.trajectory_length}."
        raise ValueError(msg)

    if agent.location.building is None:
        msg = "Agent is not located in any building. Cannot record state."
        raise ValueError(msg)

    building_idx = hash(agent.location.building) % 128  # Convert to int8 range

    agent.trajectory.push(
        time=current_time,
        building_idx=building_idx,
        floor=agent.location.floor,
        pos_x=agent.location.x,
        pos_y=agent.location.y,
        heading=agent.heading_rad,
        infection_status=agent.infection_status,
    )
