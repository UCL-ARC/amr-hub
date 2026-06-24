"""
CPU spatial queries and movement for agents against the building hierarchy.

This module isolates the spatial lookup and movement logic.
"""

from __future__ import annotations

import logging
import math
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.space.location import Location

if TYPE_CHECKING:
    from numpy.random import Generator

    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.space.building import Building
    from amr_hub_abm.space.room import Room

logger = logging.getLogger(__name__)


class SpatialQuery:
    """CPU-based spatial resolver and movement engine."""

    __slots__ = ("space",)  # noqa: RUF023

    def __init__(self, space: list[Building]) -> None:
        """Init."""
        self.space = space

    # ------------------------------------------------------------------------------
    def get_room(
        self,
        agent: Agent,
        coords: tuple[float, float] | None = None,
    ) -> Room | None:
        """Find the room containing the agent or specific coords."""
        if agent.location.building is None or agent.location.floor is None:
            return None

        # Determine coordinates to check
        check_coords = (
            coords if coords is not None else (agent.location.x, agent.location.y)
        )

        for building in self.space:
            if building.name != agent.location.building:
                continue
            for floor in building.floors:
                if floor.floor_number != agent.location.floor:
                    continue
                room = floor.find_room_by_location(check_coords)
                if room:
                    return room

        return None

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def is_target_reached(
        self,
        location: Location,
        target: Location,
        radius: float,
    ) -> bool:
        """Check whether *location* is within *radius* of *target*."""
        if location.building != target.building:
            return False
        if location.floor != target.floor:
            return False
        return location.distance_to(target) <= radius

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def estimate_time_to_reach_location(
        self, agent: Agent, target_location: Location
    ) -> float:
        """Estimate the time required to reach a target location."""
        return agent.location.distance_to(target_location) / agent.movement_speed

    def move_to_location(self, agent: Agent, new_location: Location) -> None:
        """Move the agent to a new location."""
        agent.location = new_location

    def head_to_point(self, agent: Agent, point: tuple[float, float]) -> None:
        """Set the agent's heading to face a specific point."""
        delta_x = point[0] - agent.location.x
        delta_y = point[1] - agent.location.y
        agent.heading_rad = math.atan2(delta_y, delta_x) % (2 * math.pi)

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    @staticmethod
    def propose_new_coordinates(
        coordinates: tuple[float, float],
        heading_rad: float,
        movement_speed: float,
        stochasticity: float,
        rng_generator: Generator,
    ) -> tuple[float, float]:
        """Propose a new location for agent movement."""
        stochastic_heading_rad = heading_rad + rng_generator.normal(
            0, math.radians(stochasticity)
        )
        delta_x = movement_speed * math.cos(stochastic_heading_rad)
        delta_y = movement_speed * math.sin(stochastic_heading_rad)

        delta_x = (1 + rng_generator.normal(0, stochasticity)) * delta_x
        delta_y = (1 + rng_generator.normal(0, stochasticity)) * delta_y

        return coordinates[0] + delta_x, coordinates[1] + delta_y

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def try_move_one_step(
        self,
        agent: Agent,
        max_attempts: int = 5,
    ) -> tuple[float, float]:
        """Return valid coordinates for a single movement step."""
        new_x = agent.location.x
        new_y = agent.location.y
        for _attempt in range(1, max_attempts + 1):
            new_x, new_y = self.propose_new_coordinates(
                (agent.location.x, agent.location.y),
                agent.heading_rad,
                agent.movement_speed,
                agent.stochasticity,
                agent.rng_generator,
            )
            room = self.get_room(agent, coords=(new_x, new_y))
            if room is None:
                continue

            walls = room.walls
            if not walls:
                msg = f"Room {room.name} has no walls defined."
                raise SimulationModeError(msg)

            if Location.check_intersection_with_walls(
                new_x,
                new_y,
                agent.interaction_radius,
                walls,
            ):
                continue
            return new_x, new_y

        return new_x, new_y

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def move_one_step(self, agent: Agent) -> None:
        """Move the agent one step in the direction of its heading."""
        new_x, new_y = self.try_move_one_step(agent)
        self.move_to_location(agent, replace(agent.location, x=new_x, y=new_y))

    def step_physics(self, agents: list[Any]) -> None:
        """Advance all agents by one step using the CPU engine."""
        for agent in agents:
            # Replicate the kinematic movement step
            self.move_one_step(agent)

    # ------------------------------------------------------------------------------
