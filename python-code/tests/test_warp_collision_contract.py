"""Tests-first W1a audit; failures describe unfixed Warp collision contracts."""

from __future__ import annotations

import inspect
import json
import os
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest
import warp as wp

from amr_hub_abm.spatial.engine import SpatialQuery
from amr_hub_abm.spatial.engine_gpu import GPUSpatialQuery
from amr_hub_abm.spatial.wall import Wall
from tests.collision_fixtures import make_scene
from tests.warp_collision_audit import (
    CASES,
    StepCase,
    build_scene,
    path_allowed,
    ray_hit,
    standard_step,
    warp_step,
)

if TYPE_CHECKING:
    from collections.abc import Callable

BACKENDS = tuple(os.environ.get("W1_BACKENDS", "warp-cpu,warp-cuda").split(","))


@pytest.fixture(params=BACKENDS)
def backend(request: pytest.FixtureRequest) -> str:
    """Choose an execution mode, explicitly skipping unavailable CUDA hardware."""
    value = str(request.param)
    assert value in {"standard-cpu", "warp-cpu", "warp-cuda"}
    if value == "warp-cuda" and not wp.is_cuda_available():
        pytest.skip("CUDA UNVALIDATED: no usable NVIDIA driver/device")
    return value


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_shared_step_contract(
    backend: str, case: StepCase, record_property: Callable[[str, object], None]
) -> None:
    """Accept valid complete paths, otherwise retain the original coordinates."""
    scene, proposed = build_scene(case)
    start = (scene.agent.location.x, scene.agent.location.y)
    allowed = case.attempts > 0 and path_allowed(scene, proposed)
    expected = proposed if allowed else start
    if backend == "standard-cpu":
        record_property("engine_source", inspect.getfile(SpatialQuery))
        actual = standard_step(scene, proposed)
        hit = None
    else:
        with wp.ScopedDevice("cpu" if backend == "warp-cpu" else "cuda:0"):
            engine = GPUSpatialQuery(scene.engine.space, case.attempts)
            engine.head_to_point(scene.agent, case.end if case.angle == 0 else proposed)
            hit = ray_hit(engine, start, proposed) if start != proposed else None
            actual = warp_step(engine, scene.agent)
    record_property(
        "observation",
        json.dumps(
            {
                "start": start,
                "proposed": proposed,
                "expected": expected,
                "actual": actual,
                "allowed": allowed,
                "actual_path_safe": path_allowed(build_scene(case)[0], actual),
                "mesh_ray_hit": hit,
                "float32_proposal": [
                    float(v) for v in np.array(proposed, dtype=np.float32)
                ],
            }
        ),
    )
    if not allowed:
        # Exact stationary comparison: no tolerance legitimises unsafe progress.
        assert actual == start
    else:
        # Only arrival coordinates use an approximation. Safety is checked exactly.
        assert actual == pytest.approx(expected)
        oracle_scene, _ = build_scene(case)
        assert path_allowed(oracle_scene, actual)


@pytest.mark.parametrize(
    "invalid",
    [float("nan"), float("inf"), -float("inf")],
    ids=["nan", "inf", "minus-inf"],
)
def test_nonfinite_proposal_rejected(
    backend: str, invalid: float, record_property: Callable[[str, object], None]
) -> None:
    """Numerically invalid proposals must not become physical agent coordinates."""
    scene = make_scene(start=(0.5, 1.0), end=(1.5, 1.0))
    start = (scene.agent.location.x, scene.agent.location.y)
    if backend == "standard-cpu":
        actual = standard_step(scene, (invalid, 1.0))
    else:
        with wp.ScopedDevice("cpu" if backend == "warp-cpu" else "cuda:0"):
            engine = GPUSpatialQuery(scene.engine.space)
            engine.head_to_point(scene.agent, (1.5, 1.0))
            scene.agent.movement_speed = invalid
            actual = warp_step(engine, scene.agent, direct=True)
    record_property("observed_coordinates", repr(actual))
    assert actual == start


@pytest.mark.parametrize("context", ["other-floor", "other-building"])
def test_unrelated_context_not_in_collision_query(backend: str, context: str) -> None:
    """A different floor/building must not obstruct this agent's movement query."""
    case = StepCase(context, start=(0.5, 1.0), end=(1.5, 1.0), special=context)
    scene, proposed = build_scene(case)
    if backend == "standard-cpu":
        assert standard_step(scene, proposed) == proposed
    else:
        with wp.ScopedDevice("cpu" if backend == "warp-cpu" else "cuda:0"):
            engine = GPUSpatialQuery(scene.engine.space)
            assert not ray_hit(engine, case.start, proposed)


@pytest.mark.parametrize("change", ["add-wall", "remove-wall"])
def test_geometry_changes_visible_or_rejected(backend: str, change: str) -> None:
    """Do not silently query stale wall geometry after live geometry changes."""
    scene = make_scene(doorway=change == "add-wall")
    if backend == "standard-cpu":
        engine = None
    else:
        with wp.ScopedDevice("cpu" if backend == "warp-cpu" else "cuda:0"):
            engine = GPUSpatialQuery(scene.engine.space)
    for room in scene.rooms:
        assert room.walls is not None
        if change == "add-wall":
            room.walls.append(Wall((2.0, 0.5), (2.0, 1.5)))
        else:
            room.walls[:] = [
                w for w in room.walls if w.start[0] != 2.0 or w.end[0] != 2.0
            ]
    expected_hit = change == "add-wall"
    if engine is None:
        assert standard_step(scene, (2.5, 1.0)) == (
            (1.5, 1.0) if expected_hit else (2.5, 1.0)
        )
    else:
        with wp.ScopedDevice("cpu" if backend == "warp-cpu" else "cuda:0"):
            assert ray_hit(engine, (1.5, 1.0), (2.5, 1.0)) == expected_hit


def test_threshold_pause_and_continue(backend: str) -> None:
    """A threshold endpoint must not prevent the subsequent valid doorway step."""
    scene = make_scene(doorway=True)
    if backend == "standard-cpu":
        for target in [(2.0, 1.0), (2.5, 1.0)]:
            actual = standard_step(scene, target)
            assert actual == target
            scene.agent.location = replace(
                scene.agent.location, x=actual[0], y=actual[1]
            )
    else:
        with wp.ScopedDevice("cpu" if backend == "warp-cpu" else "cuda:0"):
            engine = GPUSpatialQuery(scene.engine.space)
            for target in [(2.0, 1.0), (2.5, 1.0)]:
                engine.head_to_point(scene.agent, target)
                assert warp_step(engine, scene.agent) == target


def test_seeded_reproducibility(backend: str) -> None:
    """Fresh identical backend state must reproduce its own stochastic trajectory."""
    trajectories = []
    for _ in range(2):
        scene = make_scene(start=(0.5, 1.0), end=(0.55, 1.0))
        scene.agent.stochasticity = 0.1
        trajectory = []
        with wp.ScopedDevice("cpu" if backend != "warp-cuda" else "cuda:0"):
            engine = (
                scene.engine
                if backend == "standard-cpu"
                else GPUSpatialQuery(scene.engine.space)
            )
            for _step in range(8):
                engine.head_to_point(scene.agent, (1.5, 1.0))
                if isinstance(engine, SpatialQuery):
                    engine.move_one_step(scene.agent)
                else:
                    warp_step(engine, scene.agent)
                trajectory.append((scene.agent.location.x, scene.agent.location.y))
        trajectories.append(trajectory)
    assert trajectories[0] == trajectories[1]


def test_seeded_trajectory_wall_safety(
    backend: str, record_property: Callable[[str, object], None]
) -> None:
    """Reproducibility is not enough: every actual stochastic step must be safe."""
    scene = make_scene(start=(0.5, 1.0), end=(0.6, 1.0))
    scene.agent.stochasticity = 0.3
    with wp.ScopedDevice("cpu" if backend != "warp-cuda" else "cuda:0"):
        engine = (
            scene.engine
            if backend == "standard-cpu"
            else GPUSpatialQuery(scene.engine.space)
        )
        for step in range(40):
            initial = scene.agent.location
            engine.head_to_point(scene.agent, (3.5, 1.0))
            if isinstance(engine, SpatialQuery):
                engine.move_one_step(scene.agent)
            else:
                warp_step(engine, scene.agent)
            actual = (scene.agent.location.x, scene.agent.location.y)
            final = scene.agent.location
            scene.agent.location = initial
            safe = path_allowed(scene, actual)
            scene.agent.location = final
            record_property(
                f"step_{step}",
                json.dumps(
                    {"start": [initial.x, initial.y], "actual": actual, "safe": safe}
                ),
            )
            assert safe


def test_first_valid_proposal_stops_retrying(backend: str) -> None:
    """An accepted noisy proposal must be unaffected by a larger retry budget."""
    outcomes = []
    for attempts in [1, 5]:
        scene = make_scene(start=(0.5, 1.0), end=(0.55, 1.0))
        scene.agent.stochasticity = 0.1
        scene.engine.max_movement_attempts = attempts
        with wp.ScopedDevice("cpu" if backend != "warp-cuda" else "cuda:0"):
            engine = (
                scene.engine
                if backend == "standard-cpu"
                else GPUSpatialQuery(scene.engine.space, attempts)
            )
            engine.head_to_point(scene.agent, (1.5, 1.0))
            if isinstance(engine, SpatialQuery):
                engine.move_one_step(scene.agent)
                actual = (scene.agent.location.x, scene.agent.location.y)
            else:
                actual = warp_step(engine, scene.agent)
        outcomes.append(actual)
    assert outcomes[0] == outcomes[1]
