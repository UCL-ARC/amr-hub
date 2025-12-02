"""Module defining room-related classes for the AMR Hub ABM simulation."""

from dataclasses import dataclass, field

import shapely.geometry
import shapely.ops
from matplotlib.axes import Axes

from amr_hub_abm.exceptions import InvalidRoomError, SimulationModeError
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.content import Content
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.wall import Wall


@dataclass
class Room:
    """Representation of a room in the AMR Hub ABM simulation."""

    room_id: int
    building: Building
    floor: int
    contents: list[Content]
    doors: list[Door]
    walls: list[Wall] | None = field(default=None)
    area: float | None = field(default=None)
    region: shapely.geometry.Polygon = field(init=False)

    def __post_init__(self) -> None:
        """Post-initialization to validate room attributes."""
        if not self.walls and not self.area:
            msg = "Either walls or area must be provided to define a room."
            raise SimulationModeError(msg)

        if self.walls and self.area:
            msg = "Provide either walls or area, not both, to define a room."
            raise SimulationModeError(msg)

        if not self.area:
            self.area = self.form_region().area

        if self.area <= 0:
            msg = f"Room area must be positive. Got {self.area}."
            raise InvalidRoomError(msg)

        if self.walls and len(self.walls) < 3:  # noqa: PLR2004
            msg = "A room must have at least 3 walls to form a closed region."
            raise InvalidRoomError(msg)

        self.region = self.form_region()

    def form_region(self) -> shapely.geometry.Polygon:
        """Get the polygonal region of the room based on its walls."""
        if self.walls is None:
            msg = "Cannot form region without walls."
            raise InvalidRoomError(msg)

        merged_lines = shapely.ops.linemerge(
            [wall.line for wall in self.walls] + [door.line for door in self.doors]
        )

        polygon = shapely.ops.polygonize(merged_lines)

        if len(polygon) == 0:
            msg = "The walls do not form a valid closed region."
            raise InvalidRoomError(msg)

        return polygon[0]

    def plot(self, ax: Axes, **kwargs: dict) -> None:
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
