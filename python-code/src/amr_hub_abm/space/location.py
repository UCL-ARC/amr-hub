"""Module containing location representation for the AMR Hub ABM simulation."""

import math
from dataclasses import dataclass

from amr_hub_abm.exceptions import InvalidDistanceError


@dataclass
class Location:
    """Representation of a location in the AMR Hub ABM simulation."""

    x: float
    y: float
    floor: int
    building: str | None = None

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

        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)
