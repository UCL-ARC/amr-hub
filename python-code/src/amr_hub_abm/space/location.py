"""Module containing location representation for the AMR Hub ABM simulation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import shapely

from amr_hub_abm.exceptions import InvalidDistanceError

if TYPE_CHECKING:
    from amr_hub_abm.space.wall import Wall


@dataclass
class Location:
    """
    Representation of a location in the AMR Hub ABM simulation.

    Parameters
    ----------
    x : float
        The x-coordinate of the location.
    y : float
        The y-coordinate of the location.
    floor : int
        The floor number of the location.
    building : str | None, optional
        The building name of the location. Defaults to None, which indicates that the
        location is not associated with a specific building.

    """

    x: float
    y: float
    floor: int
    building: str | None = None

    def move(self, new_x: float, new_y: float, new_floor: int) -> None:
        """
        Move the location to new coordinates.

        Parameters
        ----------
        new_x : float
            The new x-coordinate of the location.
        new_y : float
            The new y-coordinate of the location.
        new_floor : int
            The new floor number of the location.

        """
        self.x = new_x
        self.y = new_y
        self.floor = new_floor

    def distance_to(self, other: Location) -> float:
        """
        Calculate the Euclidean distance to another location.

        Parameters
        ----------
        other : Location
            The other location to calculate the distance to.

        Returns
        -------
        float
            The Euclidean distance between the two locations.

        Raises
        ------
        InvalidDistanceError
            If the two locations are in different buildings or on different floors.

        """
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

    def check_line_of_sight(self, other: Location, walls: list[Wall]) -> bool:
        """
        Check if there is a line of sight to another location, considering walls.

        Parameters
        ----------
        other : Location
            The other location to check line of sight to.
        walls : list[Wall]
            The list of walls to consider.

        Returns
        -------
        bool
            True if there is a line of sight, False otherwise.

        """
        if self.building != other.building:
            return False

        if self.floor != other.floor:
            return False

        line_of_sight = shapely.geometry.LineString(
            [(self.x, self.y), (other.x, other.y)]
        )

        return not any(line_of_sight.crosses(wall.line) for wall in walls)

    @staticmethod
    def check_intersection_with_walls(
        loc_x: float, loc_y: float, interaction_radius: float, walls: list[Wall]
    ) -> bool:
        """
        Check if the agent intersects with any walls.

        Parameters
        ----------
        loc_x : float
            The x-coordinate of the agent's location.
        loc_y : float
            The y-coordinate of the agent's location.
        interaction_radius : float
            The radius within which the agent is considered to interact with walls.
        walls : list[Wall]
            The list of walls to consider.

        Returns
        -------
        bool
            True if the agent intersects with any walls, False otherwise.

        """
        for wall in walls:
            if (
                wall.polygon.distance(shapely.geometry.Point(loc_x, loc_y))
                < interaction_radius
            ):
                return True
        return False
