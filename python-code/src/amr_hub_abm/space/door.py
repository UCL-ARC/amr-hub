"""Module defining door representation for the AMR Hub ABM simulation."""

from abc import ABC
from dataclasses import dataclass

import shapely.geometry


@dataclass
class Door(ABC):
    """Representation of a door in the AMR Hub ABM simulation."""

    door_id: int
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


@dataclass
class TopologicalDoor(Door):
    """Representation of a topological door in the AMR Hub ABM simulation."""
