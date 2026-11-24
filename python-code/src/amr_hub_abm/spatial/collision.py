"""
Authoritative host-side swept-path checks for hybrid Warp movement.

Geometry and positions remain float64. Agents are representative points with a
minimum centre-to-physical-wall distance, not discs with an extra body radius.
Prepared geometry is reused until its source changes. A cheap value/identity
check detects edits between synchronous calls without constructing polygons.
Room regions are the model's configured coverage, as in C1.
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
    from collections.abc import Mapping, Sequence

    from numpy.typing import NDArray
    from shapely.geometry.base import BaseGeometry

    from amr_hub_abm.spatial.building import Building
    from amr_hub_abm.spatial.room import Room

type _Context = tuple[str, int]
type _WallShape = tuple[tuple[float, float], tuple[float, float], float]
type _FloorSource = tuple[tuple[int, tuple[_WallShape, ...]], ...]


@dataclass
class FloorCollisionGeometry:
    """
    Physical obstacles and configured coverage for one building/floor.

    Parameters
    ----------
    regions : tuple of BaseGeometry
        Modelled room regions, including doorway thresholds.
    walls : tuple of BaseGeometry
        Physical wall polygons, including thickness and square end caps.

    """

    regions: tuple[BaseGeometry, ...] = ()
    walls: tuple[BaseGeometry, ...] = ()
    _coverage: BaseGeometry = field(init=False)
    _region_bounds: NDArray[np.float64] = field(init=False)
    _wall_bounds: NDArray[np.float64] = field(init=False)

    def __post_init__(self) -> None:
        """Prepare coverage and conservative query bounds once at geometry load."""
        self._coverage = unary_union(self.regions)
        self._region_bounds = np.asarray(
            [region.bounds for region in self.regions], dtype=np.float64
        ).reshape(-1, 4)
        self._wall_bounds = np.asarray(
            [wall.bounds for wall in self.walls], dtype=np.float64
        ).reshape(-1, 4)

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
        bounds = self._region_bounds
        possible_rooms = np.flatnonzero(
            (bounds[:, 0] <= min_x)
            & (bounds[:, 1] <= min_y)
            & (bounds[:, 2] >= max_x)
            & (bounds[:, 3] >= max_y)
        )
        if not any(
            self.regions[i].covers(path) for i in possible_rooms
        ) and not self._coverage.covers(path):
            return False
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


def _rooms_by_context(space: Sequence[Building]) -> dict[_Context, list[Room]]:
    """Read the current hierarchy, including empty and repeated contexts."""
    contexts: dict[_Context, list[Room]] = {}
    for building in space:
        for floor in building.floors:
            contexts.setdefault((building.name, floor.floor_number), []).extend(
                floor.rooms
            )
    return contexts


def _floor_source(rooms: Sequence[Room]) -> _FloorSource:
    """Capture wall values and immutable region identities without GEOS work."""
    # Shapely regions are immutable. Prepared geometry retains their references,
    # so their identities cannot be recycled while this signature is in use.
    return tuple(
        (
            id(room.region),
            tuple(
                (
                    (wall.start[0], wall.start[1]),
                    (wall.end[0], wall.end[1]),
                    wall.thickness,
                )
                for wall in room.walls
            ),
        )
        for room in rooms
        if room.walls
    )


def _prepare_floor(rooms: Sequence[Room]) -> FloorCollisionGeometry:
    """Validate and construct the physical geometry for a changed floor."""
    regions = []
    walls = []
    for room in rooms:
        if not room.walls:
            continue
        if not room.region.is_valid:
            msg = f"Invalid modelled room region: {room.name}."
            raise SimulationModeError(msg)
        regions.append(room.region)
        for wall in room.walls:
            if (
                not all(
                    math.isfinite(v) for v in (*wall.start, *wall.end, wall.thickness)
                )
                or wall.thickness < 0
            ):
                msg = f"Invalid physical wall in room: {room.name}."
                raise SimulationModeError(msg)
            polygon = wall.polygon
            if not polygon.is_valid:
                msg = f"Invalid physical wall polygon in room: {room.name}."
                raise SimulationModeError(msg)
            walls.append(polygon)
    return FloorCollisionGeometry(tuple(regions), tuple(walls))


class CollisionGeometryCache:
    """
    Load physical geometry once and refresh only changed building/floor contexts.

    Parameters
    ----------
    space : sequence of Building
        Initial hierarchy. Mutable wall values and immutable room-region identities
        are checked before each query/batch; concurrent edits are unsupported.

    """

    def __init__(self, space: Sequence[Building]) -> None:
        """Prepare the initial floorplan before any movement is accepted."""
        self._sources: dict[_Context, _FloorSource] = {}
        self._contexts: dict[_Context, FloorCollisionGeometry] = {}
        self.get_contexts(space)

    def get_contexts(
        self, space: Sequence[Building]
    ) -> Mapping[_Context, FloorCollisionGeometry]:
        """
        Reuse prepared floors, rebuilding only new or edited contexts.

        Parameters
        ----------
        space : sequence of Building
            Current hierarchy. Removed contexts are dropped; wall additions,
            removals, endpoint/thickness edits and region replacements invalidate
            the affected context. Caller-owned coverage is not regenerated.

        Returns
        -------
        Mapping of tuple to FloorCollisionGeometry
            Validated geometry for the current hierarchy, with reusable bounds
            and coverage. Callers must not modify the prepared objects.

        Raises
        ------
        SimulationModeError
            An edited context has invalid geometry. No partial refresh is published
            and no stale result is returned; repair the input before retrying.

        """
        sources: dict[_Context, _FloorSource] = {}
        contexts: dict[_Context, FloorCollisionGeometry] = {}
        for key, rooms in _rooms_by_context(space).items():
            source = _floor_source(rooms)
            sources[key] = source
            contexts[key] = (
                self._contexts[key]
                if key in self._sources and source == self._sources[key]
                else _prepare_floor(rooms)
            )
        self._sources, self._contexts = sources, contexts
        return contexts


def snapshot_collision_geometry(
    space: Sequence[Building],
) -> dict[tuple[str, int], FloorCollisionGeometry]:
    """
    Construct a fresh prepared floorplan, without reusing any cached geometry.

    Parameters
    ----------
    space : sequence of Building
        Current hierarchy. Only rooms with physical walls define coverage, as
        in C1; area-only rooms are not a wall-collision movement mode.

    Returns
    -------
    dict of tuple to FloorCollisionGeometry
        Per-context prepared geometry. Changes to walls do not regenerate regions:
        callers must also update configured coverage when its boundary changes.

    Raises
    ------
    SimulationModeError
        A configured region or physical wall contains invalid geometry.

    """
    return {
        key: _prepare_floor(rooms) for key, rooms in _rooms_by_context(space).items()
    }
