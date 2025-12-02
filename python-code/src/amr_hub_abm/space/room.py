"""Module defining room-related classes for the AMR Hub ABM simulation."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

import shapely.geometry
import shapely.ops
from matplotlib.axes import Axes

from amr_hub_abm.exceptions import InvalidRoomError
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.content import Content
from amr_hub_abm.space.door import Door, SpatialDoor
from amr_hub_abm.space.wall import Wall


@dataclass
class Room(ABC):
    """Representation of a room in the AMR Hub ABM simulation."""

    room_id: int
    doors: Sequence[Door]
    building: Building
    floor: int
    contents: Sequence[Content]

    @abstractmethod
    def get_area(self) -> float:
        """Get the area of the room."""


@dataclass
class SpatialRoom(Room):
    """Representation of a room in the AMR Hub ABM simulation."""

    walls: Sequence[Wall]
    doors: Sequence[SpatialDoor]

    region: shapely.geometry.Polygon = field(init=False)

    def __post_init__(self) -> None:
        """Post-initialization to validate walls and doors."""
        if len(self.walls) < 3:  # noqa: PLR2004
            msg = "A room must have at least 3 walls to form a closed region."
            raise InvalidRoomError(msg)

        self.region = self.form_region()

    def form_region(self) -> shapely.geometry.Polygon:
        """Get the polygonal region of the room based on its walls."""
        merged_lines = shapely.ops.linemerge(
            [wall.line for wall in self.walls] + [door.line for door in self.doors]
        )

        polygon = shapely.ops.polygonize(merged_lines)

        if len(polygon) == 0:
            msg = "The walls do not form a valid closed region."
            raise InvalidRoomError(msg)

        return polygon[0]

    def get_area(self) -> float:
        """Get the area of the room."""
        return self.region.area

    def plot(self, ax: Axes, **kwargs: dict) -> None:
        """Plot the room on a given matplotlib axis."""
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
