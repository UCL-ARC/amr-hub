"""
CPU spatial queries and movement for agents against the building hierarchy.

This module isolates the spatial lookup and movement logic.
"""

from __future__ import annotations

import logging
import math
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

if TYPE_CHECKING:
    from numpy.random import Generator
    from shapely.geometry.base import BaseGeometry

    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.spatial.building import Building
    from amr_hub_abm.spatial.location import Location
    from amr_hub_abm.spatial.room import Room
    from amr_hub_abm.spatial.wall import Wall

logger = logging.getLogger(__name__)


class SpatialQuery:
    """CPU-based spatial resolver and movement engine."""

    __slots__ = ("max_movement_attempts", "space")

    def __init__(self, space: list[Building], max_movement_attempts: int = 5) -> None:
        """Init."""
        self.space = space
        self.max_movement_attempts = max_movement_attempts

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
    @staticmethod
    def _path_hits_wall(
        path: BaseGeometry, walls: list[Wall], clearance: float
    ) -> bool:
        """Reject exact wall contact/clearance after a conservative bounds filter."""
        min_x, min_y, max_x, max_y = path.bounds
        for wall in walls:
            # An oblique square cap extends up to sqrt(2) * half-thickness
            # in either axis. A half-thickness-only bound can miss its corners.
            padding = wall.thickness * math.sqrt(0.5) + clearance
            if (
                min(wall.start[0], wall.end[0]) - padding > max_x
                or max(wall.start[0], wall.end[0]) + padding < min_x
                or min(wall.start[1], wall.end[1]) - padding > max_y
                or max(wall.start[1], wall.end[1]) + padding < min_y
            ):
                continue
            polygon = wall.polygon
            if path.intersects(polygon) or path.distance(polygon) < clearance:
                return True
        return False

    def try_move_one_step(
        self,
        agent: Agent,
        max_attempts: int | None = None,
    ) -> tuple[float, float]:
        """
        Return a safe straight-line step, or stay put after rejected attempts.

        The whole segment must remain in modelled rooms on the agent's floor
        and avoid their physical wall polygons. ``interaction_radius`` is the
        minimum distance from the agent's representative centre to a physical
        wall polygon. Equality is allowed, but physical wall contact is rejected
        even at zero radius. Room boundaries inside doorway openings are
        traversable, including a step ending on a threshold.

        Rejected proposals never change the starting position. This is collision
        rejection, not routing or recovery from an initially invalid position.
        """
        attempts = (
            max_attempts if max_attempts is not None else self.max_movement_attempts
        )
        start = (agent.location.x, agent.location.y)
        if attempts <= 0:
            return start
        rooms = [
            room
            for building in self.space
            if building.name == agent.location.building
            for floor in building.floors
            if floor.floor_number == agent.location.floor
            for room in floor.rooms
            if room.walls
        ]
        if not rooms:
            return start
        walls = [wall for room in rooms for wall in room.walls or []]
        floor_region: BaseGeometry | None = None
        for _attempt in range(1, attempts + 1):
            new_x, new_y = self.propose_new_coordinates(
                start,
                agent.heading_rad,
                agent.movement_speed,
                agent.stochasticity,
                agent.rng_generator,
            )
            if not (math.isfinite(new_x) and math.isfinite(new_y)):
                continue
            end = (new_x, new_y)
            path = Point(start) if start == end else LineString([start, end])
            if not any(room.region.covers(path) for room in rooms):
                # Most steps stay in one room; join regions only for transitions.
                # Covers includes doorway thresholds without weakening wall checks.
                if floor_region is None:
                    floor_region = unary_union([room.region for room in rooms])
                if not floor_region.covers(path):
                    continue
            if self._path_hits_wall(path, walls, agent.interaction_radius):
                continue
            return new_x, new_y

        return start

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
