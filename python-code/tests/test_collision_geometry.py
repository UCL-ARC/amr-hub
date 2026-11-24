"""Independent polygon-oracle coverage for hybrid Warp collision geometry."""

from dataclasses import replace
from math import cos, radians, sin

import numpy as np
import pytest
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.spatial.collision import snapshot_collision_geometry
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
