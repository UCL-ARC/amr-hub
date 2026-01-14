"""Module containing location representation for the AMR Hub ABM simulation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import shapely

from amr_hub_abm.exceptions import InvalidDistanceError

if TYPE_CHECKING:
    from amr_hub_abm.space.room import Room


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

    def distance_to(self, other: Location) -> float:
        """Calculate the Euclidean distance to another location."""
        if self.building != other.building:
            raise InvalidDistanceError((self.building, other.building), building=True)
        if self.floor != other.floor:
            raise InvalidDistanceError((self.floor, other.floor), building=False)

        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def __repr__(self) -> str:
        """Return a string representation of the location."""
        return (
            f"Location(x={self.x:.2f}, y={self.y:.2f}, {self.floor}, {self.building})"
        )

    def which_room(self, rooms: list[Room]) -> Room | None:
        """Determine which room the location is in, if any."""
        for room in rooms:
            if room.building != self.building or room.floor != self.floor:
                continue
            if room.region.contains(shapely.geometry.Point(self.x, self.y)):
                return room
        return None
