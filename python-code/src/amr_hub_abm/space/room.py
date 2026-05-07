"""Module defining room-related classes for the AMR Hub ABM simulation."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import shapely.geometry
import shapely.ops

from amr_hub_abm.exceptions import InvalidRoomError, SimulationModeError
from amr_hub_abm.space.location import Location

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from numpy.random import Generator

    from amr_hub_abm.agent import Agent
    from amr_hub_abm.space.content import Content
    from amr_hub_abm.space.door import Door
    from amr_hub_abm.space.wall import Wall

logger = logging.getLogger(__name__)


@dataclass
class Room:
    """Representation of a room in the AMR Hub ABM simulation."""

    room_id: int
    name: str
    building: str
    floor: int
    contents: list[Content]
    doors: list[Door]
    rng_generator: Generator
    walls: list[Wall] | None = field(default=None)
    area: float | None = field(default=None)
    region: shapely.geometry.Polygon = field(init=False)
    room_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Post-initialization to validate room attributes."""
        if not self.walls and not self.area:
            msg = "Either walls or area must be provided to define a room."
            raise SimulationModeError(msg)

        # NG Added since you need to count doors ( Emergency, sliding etc)
        #if self.walls and len(self.walls) < 3:
        #    msg = "A room must have at least 3 walls to form a closed region."
        #    raise InvalidRoomError(msg)

        total_boundaries = len(self.walls) + len(self.doors)
        if total_boundaries < 3:
            msg = f"Invalid room definition for '{self.name}': A room must have at least 3 boundaries to form a closed region. Found {len(self.walls)} walls and {len(self.doors)} doors."
            raise InvalidRoomError(msg)

        if self.walls and self.area:
            msg = "Provide either walls or area, not both, to define a room."
            raise SimulationModeError(msg)

        if not self.area:
            self.area = self.form_region().area

        if self.area <= 0:
            msg = f"Room area must be positive. Got {self.area}."
            raise InvalidRoomError(msg)

        if self.walls:
            self.region = self.form_region()
        else:
            self.region = shapely.geometry.Polygon()
            logger.warning(
                "Room %s has no walls; region is set to an empty polygon.", self.name
            )

        self.room_hash = (
            self.create_polygon_hash() if self.walls else self.create_name_hash()
        )

        self.validate_contents()

    def __hash__(self) -> int:
        """Generate a hash for the room based on its unique hash string."""
        return hash(self.room_hash)

    def __eq__(self, other: object) -> bool:
        """Check equality of two rooms based on their unique hash strings."""
        if not isinstance(other, Room):
            return NotImplemented
        return self.room_hash == other.room_hash

    def create_polygon_hash(self) -> str:
        """Create a unique hash for the room based on its polygonal region."""
        if not self.walls:
            msg = "Cannot create polygon hash without walls."
            raise SimulationModeError(msg)

        return hashlib.sha256(shapely.ops.orient(self.region).wkb).hexdigest()

    def create_name_hash(self) -> str:
        """Create a unique hash for the room based on its name."""
        return hashlib.sha256(self.name.encode("utf-8")).hexdigest()

    # NG Updated to be general and more robust
    def form_region(self):
        """Forms a closed polygon region from the room's boundaries."""
        from shapely.ops import polygonize, unary_union
        from shapely.geometry import MultiLineString
        import logging

        boundary_lines = [wall.line for wall in self.walls] + [door.line for door in self.doors]

        if not boundary_lines:
            raise InvalidRoomError(f"Room '{self.name}' has no physical boundaries.")

        # 1. Try the strict approach: Node the lines together and polygonize
        merged_lines = unary_union(boundary_lines)
        polygons = list(polygonize(merged_lines))

        if polygons:
            # Sort by area in case it found multiple small fragments, grab the biggest one
            polygons.sort(key=lambda p: p.area, reverse=True)
            return polygons[0]

        # 2. The Convex Hull
        # If the CAD lines have tiny gaps or missing shared walls, wrap a polygon around the extents
        logger = logging.getLogger(__name__)
        logger.warning(
            f"⚠Room '{self.name}' boundaries do not perfectly connect"
            "Approximating floor area using Convex Hull"
        )

        fallback_polygon = MultiLineString(boundary_lines).convex_hull

        # If it's a perfectly flat line, it can't be a room
        if fallback_polygon.geom_type != 'Polygon' or fallback_polygon.is_empty:
            msg = f"Invalid room definition for '{self.name}': The lines do not enclose any space"
            raise InvalidRoomError(msg)

        return fallback_polygon

    def plot(
        self,
        ax: Axes,
        agents: list[Agent] | None = None,
        *,
        trajectory: bool = False,
        **kwargs: dict,
    ) -> None:
        """Plot the room on a given matplotlib axis."""
        if not self.walls:
            msg = "Cannot plot room without walls."
            raise SimulationModeError(msg)

        for wall in self.walls:
            wall.plot(ax, color="black")  # type: ignore  # noqa: PGH003

        for door in self.doors:
            x, y = door.line.xy
            ax.plot(
                x,
                y,
                color=kwargs.get("door_color", "brown"),
                linewidth=kwargs.get("door_width", 2),
            )

        for content in self.contents:
            ax.scatter(
                content.position[0],
                content.position[1],
                marker=content.marker_type,
                color=content.color,
                s=content.marker_size,
                label=f"{content.content_type.name} ({content.content_id})",
            )

        if agents is None:
            return

        for agent in agents:
            if (
                agent.location.building == self.building
                and agent.location.floor == self.floor
            ) and self.contains_point((agent.location.x, agent.location.y)):
                agent.plot_agent(ax)
                if trajectory:
                    agent.plot_trajectory(ax)

    def contains_point(self, point: tuple[float, float]) -> bool:
        """Check if a given point is inside the room."""
        if not self.walls:
            msg = "Cannot check point containment without walls."
            raise SimulationModeError(msg)

        return self.region.contains(shapely.geometry.Point(point))

    def get_random_point(self, max_attempts: int = 1000) -> tuple[float, float]:
        """Get a random point within the room."""
        if not self.walls:
            msg = "Cannot get random point without walls."
            raise SimulationModeError(msg)

        minx, miny, maxx, maxy = self.region.bounds

        for _ in range(max_attempts):
            # If required later... Improve efficiency using batching or spatial indexing
            random_point = shapely.geometry.Point(
                self.rng_generator.uniform(minx, maxx),
                self.rng_generator.uniform(miny, maxy),
            )
            if self.region.contains(
                random_point
            ) and not Location.check_intersection_with_walls(
                random_point.x, random_point.y, 0.1, self.walls
            ):
                return (random_point.x, random_point.y)

        msg = f"""
        Failed to find a random point within the room after {max_attempts} attempts.
        Consider increasing max_attempts or checking room geometry.
        """
        raise SimulationModeError(msg)

    def get_door_access_point(self) -> tuple[Door, tuple[float, float]]:
        """Get a point near one of the room's doors for access."""
        if not self.doors:
            msg = f"Room {self.name} has no doors for access."
            raise InvalidRoomError(msg)

        if len(self.doors) > 1:
            msg = f"Room {self.name} has multiple doors; \
            This functionality is not supported for now."
            raise InvalidRoomError(msg)

        door = self.doors[0]
        midpoint = door.line.interpolate(0.5, normalized=True)
        return (door, (midpoint.x, midpoint.y))

    def validate_contents(self) -> None:
        """Validate that all contents are located within the room."""
        if not self.walls:
            return

        for content in self.contents:
            if not self.contains_point(content.position):
                msg = f"Content {content.content_id} of type {content.content_type} "
                msg += f"is located at {content.position}, which is outside the room."
                raise InvalidRoomError(msg)
