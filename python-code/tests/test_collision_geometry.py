"""Independent polygon-oracle coverage for hybrid Warp collision geometry."""

from dataclasses import replace
from math import cos, radians, sin
from unittest.mock import patch

import numpy as np
import pytest
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.spatial.collision import (
    CollisionGeometryCache,
    snapshot_collision_geometry,
)
from amr_hub_abm.spatial.floor import Floor
from tests.collision_fixtures import BUILDING, make_scene


@pytest.mark.parametrize("angle", [0.0, 45.0, 90.0, 135.0])
@pytest.mark.parametrize("clearance", [0.0, 0.01, 0.1])
@pytest.mark.parametrize("doorway", [False, True])
def test_snapshot_matches_independent_exhaustive_oracle(
    angle: float, clearance: float, *, doorway: bool
) -> None:
    """No candidate filter may omit a physical wall or its clearance."""
    rng = np.random.default_rng(262)
    theta = radians(angle)
    for _ in range(15):
        start = (float(rng.uniform(0.3, 1.7)), float(rng.uniform(0.3, 1.7)))
        scene = make_scene(
            start=start, doorway=doorway, radius=clearance, angle_degrees=angle
        )
        x, y = float(rng.uniform(0.2, 3.8)), float(rng.uniform(0.2, 1.8))
        end = (x * cos(theta) - y * sin(theta), x * sin(theta) + y * cos(theta))
        path = LineString([(scene.agent.location.x, scene.agent.location.y), end])
        expected = unary_union([room.region for room in scene.rooms]).covers(path)
        expected &= not any(
            path.intersects(wall.polygon) or path.distance(wall.polygon) < clearance
            for room in scene.rooms
            for wall in room.walls or []
        )
        geometry = snapshot_collision_geometry(scene.engine.space)[(BUILDING, 0)]
        assert (
            geometry.allows(
                (scene.agent.location.x, scene.agent.location.y), end, clearance
            )
            == expected
        )


@pytest.mark.parametrize("hole", [False, True])
def test_covered_endpoints_do_not_allow_uncovered_middle(*, hole: bool) -> None:
    """Respect both nonconvex coverage and a hole without adding obstacle walls."""
    scene = make_scene(doorway=True)
    if hole:
        region = Polygon(
            [(0, 0), (4, 0), (4, 2), (0, 2)],
            holes=[[(1.8, 0.75), (2.2, 0.75), (2.2, 1.25), (1.8, 1.25)]],
        )
    else:
        region = Polygon(
            [(0, 0), (4, 0), (4, 2), (2.2, 2), (2.2, 0.5), (1.8, 0.5), (1.8, 2), (0, 2)]
        )
    for room in scene.rooms:
        room.region = region
    assert region.covers(Point(1.5, 1.0))
    assert region.covers(Point(2.5, 1.0))
    geometry = snapshot_collision_geometry(scene.engine.space)[(BUILDING, 0)]
    assert not geometry.allows((1.5, 1.0), (2.5, 1.0), 0.01)


@pytest.mark.parametrize("invalid", ["wall", "region"])
def test_invalid_live_geometry_raises_domain_error(invalid: str) -> None:
    """Invalid edits cannot silently drop collision constraints from a snapshot."""
    scene = make_scene()
    if invalid == "wall":
        assert scene.rooms[0].walls is not None
        scene.rooms[0].walls[0] = replace(scene.rooms[0].walls[0], thickness=-1.0)
    else:
        scene.rooms[0].region = Polygon([(0, 0), (1, 1), (0, 1), (1, 0)])
    with pytest.raises(SimulationModeError):
        snapshot_collision_geometry(scene.engine.space)


def test_cached_floors_reuse_coverage_and_bounds() -> None:
    """All geometry preparation is done at load, not in later movement queries."""
    scene = make_scene(doorway=True)
    with patch(
        "amr_hub_abm.spatial.collision.unary_union", wraps=unary_union
    ) as unions:
        cache = CollisionGeometryCache(scene.engine.space)
        loaded = cache.get_contexts(scene.engine.space)[(BUILDING, 0)]
        assert unions.call_count == 1
        for _ in range(3):
            geometry = cache.get_contexts(scene.engine.space)[(BUILDING, 0)]
            assert geometry is loaded
            assert geometry.allows((1.5, 1.0), (2.5, 1.0), 0.01)
        assert unions.call_count == 1


@pytest.mark.parametrize(
    "change", ["region", "room", "wall-list", "wallless", "context-remove", "rename"]
)
def test_cache_tracks_geometry_and_hierarchy_changes(change: str) -> None:
    """Replacing coverage or hierarchy refreshes only the affected context."""
    scene, other = make_scene(doorway=True), make_scene(doorway=True)
    building = scene.engine.space[0]
    building.floors.append(Floor(1, other.rooms))
    cache = CollisionGeometryCache(scene.engine.space)
    original = cache.get_contexts(scene.engine.space)
    if change == "region":
        scene.rooms[0].region = Polygon([(0, 0), (1, 0), (1, 2), (0, 2)])
    elif change == "room":
        building.floors[0].rooms = [scene.rooms[1]]
    elif change == "wall-list":
        assert scene.rooms[0].walls is not None
        scene.rooms[0].walls = [
            replace(wall, thickness=0.5) for wall in scene.rooms[0].walls
        ]
    elif change == "wallless":
        for room in scene.rooms:
            room.walls = None
    elif change == "context-remove":
        building.floors.pop(0)
    else:
        building.name = "Renamed"
    current = cache.get_contexts(scene.engine.space)
    fresh = snapshot_collision_geometry(scene.engine.space)
    assert current.keys() == fresh.keys()
    if change != "rename":
        assert current[(BUILDING, 1)] is original[(BUILDING, 1)]
    if (BUILDING, 0) in current:
        assert current[(BUILDING, 0)] is not original[(BUILDING, 0)]
    for key, geometry in current.items():
        for start, end in [((1.5, 1.0), (2.5, 1.0)), ((0.5, 1.0), (1.5, 1.0))]:
            assert geometry.allows(start, end, 0.01) == fresh[key].allows(
                start, end, 0.01
            )


def test_invalid_refresh_is_atomic_and_recoverable() -> None:
    """A later invalid context cannot publish partially refreshed earlier floors."""
    scene, other = make_scene(doorway=True), make_scene(doorway=True)
    scene.engine.space[0].floors.append(Floor(1, other.rooms))
    cache = CollisionGeometryCache(scene.engine.space)
    original = cache.get_contexts(scene.engine.space)
    assert scene.rooms[0].walls is not None
    assert other.rooms[0].walls is not None
    wall = scene.rooms[0].walls[0]
    wall.thickness = 0.5
    bad_wall = other.rooms[0].walls[0]
    bad_wall.thickness = -1
    for _ in range(2):
        with pytest.raises(SimulationModeError):
            cache.get_contexts(scene.engine.space)
    wall.thickness = 0.2
    bad_wall.thickness = 0.2
    restored = cache.get_contexts(scene.engine.space)
    assert all(restored[key] is geometry for key, geometry in original.items())
