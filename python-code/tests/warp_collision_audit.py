"""Synthetic contracts and real-kernel adapters for the W1a collision audit."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import TYPE_CHECKING
from unittest.mock import patch

import warp as wp
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from amr_hub_abm.spatial.building import Building
from amr_hub_abm.spatial.engine import SpatialQuery
from amr_hub_abm.spatial.engine_gpu import (
    GPUSpatialQuery,
    cuda_warp_kernel_kinematic_agent_movement,
)
from amr_hub_abm.spatial.floor import Floor
from amr_hub_abm.spatial.wall import Wall
from tests.collision_fixtures import (
    BUILDING,
    CollisionScene,
    make_room,
    make_row_scene,
    make_scene,
)

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent


@dataclass(frozen=True)
class StepCase:
    """Describe one finite proposal without sharing mutable simulation state."""

    name: str
    start: tuple[float, float] = (1.5, 1.0)
    end: tuple[float, float] = (2.5, 1.0)
    doorway: bool = False
    radius: float = 0.01
    angle: float = 0.0
    thickness: float = 0.2
    attempts: int = 5
    special: str = ""


CASES = (
    StepCase("solid-forward"),
    StepCase("solid-reverse", start=(2.5, 1.0), end=(1.5, 1.0)),
    StepCase("solid-oblique", angle=45.0),
    StepCase("solid-horizontal", angle=90.0),
    StepCase("solid-zero-clearance", radius=0.0),
    StepCase("exhaustion-one-attempt", attempts=1),
    StepCase("exhaustion-zero-attempts", attempts=0),
    StepCase("exhaustion-negative-attempts", attempts=-1),
    StepCase("unobstructed", start=(0.5, 1.0), end=(1.5, 1.0)),
    StepCase("valid-zero-attempts", start=(0.5, 1.0), end=(1.5, 1.0), attempts=0),
    StepCase("door-forward", doorway=True),
    StepCase("door-reverse", doorway=True, start=(2.5, 1.0), end=(1.5, 1.0)),
    StepCase("door-oblique", doorway=True, angle=45.0),
    StepCase("door-horizontal", doorway=True, angle=90.0),
    StepCase("door-threshold", doorway=True, end=(2.0, 1.0)),
    StepCase("jamb-physical-cap", doorway=True, start=(1.5, 0.55), end=(2.5, 0.55)),
    StepCase("jamb-clearance", doorway=True, start=(1.5, 0.605), end=(2.5, 0.605)),
    StepCase("jamb-safe", doorway=True, start=(1.5, 0.625), end=(2.5, 0.625)),
    StepCase(
        "square-cap-oblique",
        doorway=True,
        start=(2.5, 0.58),
        end=(2.08, 0.58),
        radius=0.0,
        angle=45.0,
    ),
    StepCase(
        "physical-thickness-before-centreline",
        end=(1.9375, 1.0),
        thickness=0.25,
        radius=0.0,
    ),
    StepCase(
        "positive-clearance-too-close",
        start=(0.5, 0.34375),
        end=(1.5, 0.34375),
        radius=0.25,
        thickness=0.25,
    ),
    StepCase(
        "positive-clearance-equality",
        start=(0.5, 0.375),
        end=(1.5, 0.375),
        radius=0.25,
        thickness=0.25,
    ),
    StepCase(
        "positive-clearance-outside",
        start=(0.5, 0.40625),
        end=(1.5, 0.40625),
        radius=0.25,
        thickness=0.25,
    ),
    StepCase(
        "zero-clearance-contact",
        start=(0.5, 0.5),
        end=(1.5, 0.125),
        radius=0.0,
        thickness=0.25,
    ),
    StepCase(
        "initial-overlap-no-recovery",
        start=(1.9375, 1.0),
        end=(1.5, 1.0),
        thickness=0.25,
    ),
    StepCase("stationary", end=(1.5, 1.0)),
    StepCase("zero-speed", start=(0.5, 1.0), end=(1.5, 1.0), special="zero-speed"),
    StepCase("outside-floor", end=(4.5, 1.0)),
    StepCase("unmodelled-gap", doorway=True, end=(3.5, 1.0), special="gap"),
    StepCase("intermediate-solid", end=(7.0, 1.0), special="row-solid"),
    StepCase("intermediate-open", end=(7.0, 1.0), special="row-open"),
    StepCase(
        "missing-floor", start=(0.5, 1.0), end=(1.5, 1.0), special="missing-floor"
    ),
    StepCase(
        "missing-building", start=(0.5, 1.0), end=(1.5, 1.0), special="missing-building"
    ),
    StepCase("other-floor", start=(0.5, 1.0), end=(1.5, 1.0), special="other-floor"),
    StepCase(
        "other-building", start=(0.5, 1.0), end=(1.5, 1.0), special="other-building"
    ),
)


def build_scene(case: StepCase) -> tuple[CollisionScene, tuple[float, float]]:
    """Build a fresh scene and its requested deterministic endpoint."""
    scene = make_scene(
        start=case.start,
        end=case.end,
        doorway=case.doorway,
        radius=case.radius,
        angle_degrees=case.angle,
    )
    proposed = scene.engine.propose_new_coordinates(
        case.start
        if case.angle == 0
        else (scene.agent.location.x, scene.agent.location.y),
        scene.agent.heading_rad,
        scene.agent.movement_speed,
        0.0,
        scene.agent.rng_generator,
    )
    # Nonrotated candidates are stated explicitly to test binary-exact boundaries.
    if case.angle == 0:
        proposed = case.end
    for room in scene.rooms:
        for wall in room.walls or []:
            wall.thickness = case.thickness
    if case.special == "zero-speed":
        scene.agent.movement_speed = 0.0
        proposed = (scene.agent.location.x, scene.agent.location.y)
    elif case.special == "gap":
        right = scene.rooms[1]
        walls = [
            Wall((w.start[0] + 1, w.start[1]), (w.end[0] + 1, w.end[1]))
            for w in right.walls or []
        ]
        doors = [replace(d, start=(3.0, 0.5), end=(3.0, 1.5)) for d in right.doors]
        scene.rooms[1] = make_room(walls, room_id=1, doors=doors)
    elif case.special.startswith("row-"):
        scene = make_row_scene((True, case.special == "row-open", True))
        scene.agent.movement_speed = 5.5
        proposed = case.end
    elif case.special == "missing-floor":
        scene.agent.location = replace(scene.agent.location, floor=10)
    elif case.special == "missing-building":
        scene.agent.location = replace(scene.agent.location, building="Unknown")
    elif case.special in {"other-floor", "other-building"}:
        name, level = (
            ("Other", 0) if case.special == "other-building" else (BUILDING, 1)
        )
        extra = make_room(
            [
                Wall((1.0, 0.25), (1.0, 1.75)),
                Wall((1.0, 1.75), (1.25, 1.75)),
                Wall((1.25, 1.75), (1.25, 0.25)),
                Wall((1.25, 0.25), (1.0, 0.25)),
            ],
            building=name,
            floor=level,
        )
        if name == BUILDING:
            scene.engine.space[0].floors.append(Floor(level, [extra]))
        else:
            scene.engine.space.append(Building(name, [Floor(level, [extra])]))
    scene.engine.max_movement_attempts = case.attempts
    return scene, proposed


def path_allowed(scene: CollisionScene, end: tuple[float, float]) -> bool:
    """Apply an exhaustive physical-polygon oracle without candidate filtering."""
    start = (scene.agent.location.x, scene.agent.location.y)
    if not all(isfinite(v) for v in (*start, *end)):
        return False
    rooms = [
        r
        for b in scene.engine.space
        if b.name == scene.agent.location.building
        for f in b.floors
        if f.floor_number == scene.agent.location.floor
        for r in f.rooms
        if r.walls
    ]
    if not rooms:
        return False
    path = Point(start) if start == end else LineString([start, end])
    if not unary_union([r.region for r in rooms]).covers(path):
        return False
    return not any(
        path.intersects(w.polygon)
        or path.distance(w.polygon) < scene.agent.interaction_radius
        for r in rooms
        for w in r.walls or []
    )


def standard_step(
    scene: CollisionScene, proposal: tuple[float, float]
) -> tuple[float, float]:
    """Inject only the deterministic proposal; keep the C1 rejection code real."""
    with patch.object(SpatialQuery, "propose_new_coordinates", return_value=proposal):
        return scene.engine.try_move_one_step(scene.agent)


def warp_step(
    engine: GPUSpatialQuery, agent: Agent, *, direct: bool = False
) -> tuple[float, float]:
    """Use the public physics wrapper, or its real movement kernel for NaN cases."""
    if not direct:
        engine.step_physics([agent])
        return agent.location.x, agent.location.y
    # Never feed NaN/Inf output into the unrelated proximity HashGrid.
    positions: wp.array[wp.vec3] = wp.array(
        [[agent.location.x, agent.location.y, 1.0]], dtype=wp.vec3
    )
    wp.launch(
        cuda_warp_kernel_kinematic_agent_movement,
        dim=1,
        inputs=[
            engine.mesh.id,
            positions,
            wp.array([[agent.target_x, agent.target_y]], dtype=wp.vec2),
            wp.array([agent.movement_speed], dtype=float),
            wp.array([agent.stochasticity], dtype=float),
            wp.array([agent.interaction_radius], dtype=float),
            engine.current_tick,
            engine.max_movement_attempts,
        ],
    )
    actual = positions.numpy()[0]
    return float(actual[0]), float(actual[1])


@wp.kernel
def mesh_ray_probe(
    mesh: wp.uint64,
    start: wp.vec3,
    end: wp.vec3,
    hits: wp.array(dtype=wp.int32),  # type: ignore[valid-type]
) -> None:
    """Expose real mesh-query hits independently of unsafe fallback handling."""
    delta = end - start
    # Warp's runtime DSL supports these operations; its Python stubs omit the
    # query result and type normalize() generically rather than preserving vec3.
    hit = wp.mesh_query_ray(
        mesh,
        start,
        wp.normalize(delta),  # type: ignore[arg-type]
        wp.length(delta),
        wp.int32(0),
    )
    hits[0] = wp.int32(hit.result)  # type: ignore[attr-defined]


def ray_hit(
    engine: GPUSpatialQuery, start: tuple[float, float], end: tuple[float, float]
) -> bool:
    """Query the production mesh without replacing or mocking its geometry."""
    hits = wp.zeros(1, dtype=wp.int32)
    wp.launch(
        mesh_ray_probe,
        dim=1,
        inputs=[engine.mesh.id, wp.vec3(*start, 1.0), wp.vec3(*end, 1.0), hits],
    )
    return bool(hits.numpy()[0])
