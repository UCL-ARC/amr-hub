"""Module containing space-related classes for the AMR Hub ABM simulation."""

from abc import ABC, abstractmethod
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
class Door:
    """Representation of a door in the AMR Hub ABM simulation."""

    open: bool
    connecting_rooms: tuple[int, int]
    access_control: tuple[bool, bool]


@dataclass
class SpatialDoor(Door):
    """Representation of a door in the AMR Hub ABM simulation."""

    start: tuple[float, float]
    end: tuple[float, float]

    @property
    def line(self) -> shapely.geometry.LineString:
        """Get the line representation of the door."""
        return shapely.geometry.LineString([self.start, self.end])


class Content:
    """Enumeration of possible room contents."""


@dataclass
class Bed(Content):
    """Representation of a bed in the AMR Hub ABM simulation."""

    bed_id: int


@dataclass
class Workstation(Content):
    """Representation of a workstation in the AMR Hub ABM simulation."""

    workstation_id: int


@dataclass
class Room(ABC):
    """Representation of a room in the AMR Hub ABM simulation."""

    room_id: int
    doors: list[Door]
    building: Building
    floor: int
    contents: list[Content]

    @abstractmethod
    def get_area(self) -> float:
        """Get the area of the room."""


@dataclass
class SpatialRoom(Room):
    """Representation of a room in the AMR Hub ABM simulation."""

    walls: list[Wall]
    doors: list[SpatialDoor]

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
