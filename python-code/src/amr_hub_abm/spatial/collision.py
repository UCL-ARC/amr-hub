"""
Authoritative host-side swept-path checks for hybrid Warp movement.

Geometry and positions remain float64. Agents are representative points with a
minimum centre-to-physical-wall distance, not discs with an extra body radius.
Snapshots are scoped to one synchronous physics call, never cached across live
geometry edits. Room regions are the model's configured coverage, as in C1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from amr_hub_abm.exceptions import SimulationModeError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray
    from shapely.geometry.base import BaseGeometry

    from amr_hub_abm.spatial.building import Building


@dataclass
class FloorCollisionGeometry:
    """
    Physical obstacles and configured coverage for one building/floor.

    Parameters
    ----------
    regions : list of BaseGeometry
        Modelled room regions, including doorway thresholds.
    walls : list of BaseGeometry
        Physical wall polygons, including thickness and square end caps.

    """

    regions: list[BaseGeometry] = field(default_factory=list)
    walls: list[BaseGeometry] = field(default_factory=list)
    _coverage: BaseGeometry | None = field(default=None, init=False)
    _region_bounds: NDArray[np.float64] | None = field(default=None, init=False)
    _wall_bounds: NDArray[np.float64] | None = field(default=None, init=False)

    def allows(
        self, start: tuple[float, float], end: tuple[float, float], clearance: float
    ) -> bool:
        """
        Check the complete segment without relaxing any safety boundary.

        Parameters
        ----------
        start, end : tuple of float
            Representative-centre coordinates in the floor's coordinate system.
        clearance : float
            Minimum distance to a physical wall. Equality is allowed; contact
            with the physical wall itself is always rejected, even at zero.

        Returns
        -------
        bool
            Whether the entire finite segment is covered and avoids all walls.

        """
        if (
            not all(math.isfinite(v) for v in (*start, *end, clearance))
            or clearance < 0
        ):
            return False
        path = Point(start) if start == end else LineString([start, end])
        min_x, min_y, max_x, max_y = path.bounds
        # These are conservative vectorised bounds filters, not another spatial
        # index. The exact polygon checks below remain the acceptance authority.
        if self._region_bounds is None:
            self._region_bounds = np.asarray(
                [region.bounds for region in self.regions], dtype=np.float64
            ).reshape(-1, 4)
        bounds = self._region_bounds
        possible_rooms = np.flatnonzero(
            (bounds[:, 0] <= min_x)
            & (bounds[:, 1] <= min_y)
            & (bounds[:, 2] >= max_x)
            & (bounds[:, 3] >= max_y)
        )
        if not any(self.regions[i].covers(path) for i in possible_rooms):
            if self._coverage is None:
                self._coverage = unary_union(self.regions)
            if not self._coverage.covers(path):
                return False
        if self._wall_bounds is None:
            self._wall_bounds = np.asarray(
                [wall.bounds for wall in self.walls], dtype=np.float64
            ).reshape(-1, 4)
        bounds = self._wall_bounds
        possible_walls = np.flatnonzero(
            (bounds[:, 0] - clearance <= max_x)
            & (bounds[:, 1] - clearance <= max_y)
            & (bounds[:, 2] + clearance >= min_x)
            & (bounds[:, 3] + clearance >= min_y)
        )
        for index in possible_walls:
            wall = self.walls[index]
            if wall.is_empty:
                continue
            if path.intersects(wall) or path.distance(wall) < clearance:
                return False
        return True


def snapshot_collision_geometry(
    space: Sequence[Building],
) -> dict[tuple[str, int], FloorCollisionGeometry]:
    """
    Read live wall shapes and room regions once per synchronous physics call.

    Parameters
    ----------
    space : sequence of Building
        Current hierarchy. Only rooms with physical walls define coverage, as
        in C1; area-only rooms are not a wall-collision movement mode.

    Returns
    -------
    dict of tuple to FloorCollisionGeometry
        Per-context snapshots. Discard after the call; do not mutate their lists
        after querying them. Changes to walls do not regenerate room regions:
        callers must also update configured coverage when its boundary changes.

    Raises
    ------
    SimulationModeError
        A configured region or physical wall contains invalid geometry.

    """
    contexts: dict[tuple[str, int], FloorCollisionGeometry] = {}
    for building in space:
        for floor in building.floors:
            geometry = contexts.setdefault(
                (building.name, floor.floor_number), FloorCollisionGeometry()
            )
            for room in floor.rooms:
                if not room.walls:
                    continue
                if not room.region.is_valid:
                    msg = f"Invalid modelled room region: {room.name}."
                    raise SimulationModeError(msg)
                geometry.regions.append(room.region)
                for wall in room.walls:
                    if (
                        not all(
                            math.isfinite(v)
                            for v in (*wall.start, *wall.end, wall.thickness)
                        )
                        or wall.thickness < 0
                    ):
                        msg = f"Invalid physical wall in room: {room.name}."
                        raise SimulationModeError(msg)
                    polygon = wall.polygon
                    if not polygon.is_valid:
                        msg = f"Invalid physical wall polygon in room: {room.name}."
                        raise SimulationModeError(msg)
                    geometry.walls.append(polygon)
    return contexts
