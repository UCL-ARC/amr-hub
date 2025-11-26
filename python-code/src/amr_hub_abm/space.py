"""Module containing space-related classes for the AMR Hub ABM simulation."""

from dataclasses import dataclass, field

import shapely.geometry
import shapely.ops
from matplotlib.axes import Axes

from amr_hub_abm.exceptions import InvalidDistanceError, InvalidRoomError


@dataclass
class Building:
    """Representation of a building in the AMR Hub ABM simulation."""

    name: str


@dataclass
class Location:
    """Representation of a location in the AMR Hub ABM simulation."""

    x: float
    y: float
    floor: int
    building: Building | None = None

    def move(self, new_x: float, new_y: float, new_floor: int) -> None:
        """Move the location to new coordinates."""
        self.x = new_x
        self.y = new_y
        self.floor = new_floor

    def distance_to(self, other: "Location") -> float:
        """Calculate the Euclidean distance to another location."""
        if self.building != other.building:
            raise InvalidDistanceError((self.building, other.building), building=True)
        if self.floor != other.floor:
            raise InvalidDistanceError((self.floor, other.floor), building=False)

        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


@dataclass
class Wall:
    """Representation of a wall in the AMR Hub ABM simulation."""

    start: tuple[float, float]
    end: tuple[float, float]
    thickness: float = 0.2

    @property
    def line(self) -> shapely.geometry.LineString:
        """Get the line representation of the wall."""
        return shapely.geometry.LineString([self.start, self.end])

    @property
    def polygon(self) -> shapely.geometry.Polygon:
        """Get the polygon representation of the wall based on its thickness."""
        line = self.line
        return line.buffer(self.thickness / 2, cap_style="square")

    def plot(self, ax: Axes, **kwargs: dict) -> None:
        """Plot the wall on a given matplotlib axis."""
        x, y = self.polygon.exterior.xy
        ax.fill(x, y, **kwargs)  # pyright: ignore[reportArgumentType]


@dataclass
class Room:
    """Representation of a room in the AMR Hub ABM simulation."""

    room_id: int
    walls: list[Wall]
    doors: list[shapely.geometry.LineString]

    building: Building | None = None
    floor: int | None = None

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
            [wall.line for wall in self.walls] + self.doors
        )
        polygon = shapely.ops.polygonize(merged_lines)

        if len(polygon) == 0:
            msg = "The walls do not form a valid closed region."
            raise InvalidRoomError(msg)

        return polygon[0]

    def plot(self, ax: Axes, **kwargs: dict) -> None:
        """Plot the room on a given matplotlib axis."""
        for wall in self.walls:
            wall.plot(ax, color="black")  # type: ignore  # noqa: PGH003

        for door in self.doors:
            x, y = door.xy
            ax.plot(
                x,
                y,
                color=kwargs.get("door_color", "brown"),
                linewidth=kwargs.get("door_width", 2),
            )


def create_basic_room(
    room_id: int,
    walls: list[Wall],
    doors: list[shapely.geometry.LineString],
) -> Room:
    """Create a basic rectangular room with given width and height."""
    return Room(room_id=room_id, walls=walls, doors=doors)


if __name__ == "__main__":
    # Example usage

    wall1 = Wall(start=(0, 0), end=(5, 0))
    wall2 = Wall(start=(5, 0), end=(5, 5))
    wall3 = Wall(start=(5, 5), end=(0, 5))
    wall4 = Wall(start=(0, 5), end=(0, 0))

    wall5 = Wall(start=(1, 1), end=(1, 2))
    wall6 = Wall(start=(1, 2), end=(2, 2))
    wall7 = Wall(start=(2, 2), end=(2, 1))
    wall8 = Wall(start=(2, 1), end=(1, 1))

    room = Room(
        room_id=1,
        walls=[wall1, wall2, wall3, wall4, wall5, wall6, wall7, wall8],
        doors=[],
    )

    # check if a point is inside the room
    point = shapely.geometry.Point(1.5, 1.5)
