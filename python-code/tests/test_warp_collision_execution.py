"""End-to-end regression contracts for hybrid Warp collision enforcement."""

from dataclasses import replace
from math import nan

import numpy as np
import pytest
import warp as wp

from amr_hub_abm.agent.enums import InfectionStatus
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.spatial.building import Building
from amr_hub_abm.spatial.engine_gpu import GPUSpatialQuery
from amr_hub_abm.spatial.floor import Floor
from amr_hub_abm.spatial.wall import Wall
from tests.collision_fixtures import BUILDING, make_scene
from tests.warp_collision_audit import path_allowed


@pytest.fixture(params=["cpu", "cuda:0"])
def device(request: pytest.FixtureRequest) -> str:
    """Skip unavailable CUDA explicitly rather than substituting CPU results."""
    value = str(request.param)
    if value != "cpu" and not wp.is_cuda_available():
        pytest.skip("CUDA UNVALIDATED: no usable NVIDIA driver/device")
    return value


@pytest.mark.parametrize("other_building", [False, True])
def test_mixed_context_batch_uses_each_agents_walls(
    device: str, *, other_building: bool
) -> None:
    """Coincident open and closed floorplans must produce different outcomes."""
    open_scene, closed_scene = make_scene(doorway=True), make_scene()
    name, floor = ("Other", 0) if other_building else (BUILDING, 1)
    closed_scene.agent.idx = 1
    closed_scene.agent.location = replace(
        closed_scene.agent.location, building=name, floor=floor
    )
    space = open_scene.engine.space
    if other_building:
        space.append(Building(name, [Floor(floor, closed_scene.rooms)]))
    else:
        space[0].floors.append(Floor(floor, closed_scene.rooms))
    agents = [open_scene.agent, closed_scene.agent]
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(space)
        for agent in agents:
            engine.head_to_point(agent, (2.5, 1.0))
        engine.step_physics(agents)
    assert agents[0].location.x == 2.5
    assert agents[1].location.x == 1.5
    assert engine.telemetry[-1][:, 1].tolist() == [0, 1]


@pytest.mark.parametrize("other_building", [False, True])
def test_context_changes_between_calls_use_current_membership(
    device: str, *, other_building: bool
) -> None:
    """Reusing buffers must not pin an agent to its former building or floor."""
    scene, closed = make_scene(doorway=True), make_scene()
    initial = scene.agent.location
    name, floor = ("Other", 0) if other_building else (BUILDING, 1)
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        engine.head_to_point(scene.agent, (initial.x, initial.y))
        engine.step_physics([scene.agent])
        if other_building:
            scene.engine.space.append(Building(name, [Floor(floor, closed.rooms)]))
        else:
            scene.engine.space[0].floors.append(Floor(floor, closed.rooms))
        scene.agent.location = replace(initial, building=name, floor=floor)
        engine.head_to_point(scene.agent, (2.5, 1.0))
        engine.step_physics([scene.agent])
        assert scene.agent.location.x == initial.x
        scene.agent.location = initial
        engine.step_physics([scene.agent])
    assert scene.agent.location.x == 2.5


@pytest.mark.parametrize("change", ["add", "remove", "move", "thicken"])
def test_live_wall_changes_affect_next_step(device: str, change: str) -> None:
    """Do not reuse stale wall polygons across separate physics calls."""
    scene = make_scene(doorway=change != "remove")
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        engine.head_to_point(
            scene.agent, (scene.agent.location.x, scene.agent.location.y)
        )
        engine.step_physics([scene.agent])
        engine.head_to_point(scene.agent, (2.5, 1.0))
        if change == "add":
            for room in scene.rooms:
                assert room.walls is not None
                room.walls.append(Wall((2.0, 0.5), (2.0, 1.5)))
        elif change == "remove":
            for room in scene.rooms:
                assert room.walls is not None
                room.walls[:] = [
                    w for w in room.walls if w.start[0] != 2.0 or w.end[0] != 2.0
                ]
        else:
            # The jamb used to end at 0.5; its live shape now intersects y=1.
            for room in scene.rooms:
                for wall in room.walls or []:
                    if wall.start == (2.0, 0.0):
                        if change == "move":
                            wall.end = (2.0, 1.25)
                        else:
                            wall.thickness = 1.25
        engine.step_physics([scene.agent])
    assert scene.agent.location.x == (2.5 if change == "remove" else 1.5)


@pytest.mark.parametrize("stationary", [False, True])
def test_rejection_preserves_nonbinary_host_coordinates(
    device: str, *, stationary: bool
) -> None:
    """Rejected/idle steps do not silently round the host position to float32."""
    start = (1.500000001, 1.000000001)
    scene = make_scene(start=start, end=start if stationary else (2.5, 1.0))
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        engine.head_to_point(scene.agent, start if stationary else (2.5, 1.0))
        engine.step_physics([scene.agent], batch_steps=3)
    assert (scene.agent.location.x, scene.agent.location.y) == start


@pytest.mark.parametrize("offset", [-1e-9, 0.0, 1e-9])
def test_near_clearance_does_not_round_into_permission(
    device: str, offset: float
) -> None:
    """Check the actual float64 step against the physical, unrelaxed boundary."""
    scene = make_scene(start=(0.5, 0.5), end=(1.5, 0.375 + offset), radius=0.25)
    for room in scene.rooms:
        for wall in room.walls or []:
            wall.thickness = 0.25
    start = scene.agent.location
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        engine.head_to_point(scene.agent, (1.5, 0.375 + offset))
        engine.step_physics([scene.agent])
    actual = (scene.agent.location.x, scene.agent.location.y)
    scene.agent.location = start
    assert path_allowed(scene, actual)
    assert (actual == (start.x, start.y)) == (offset < 0)


def test_batch_matches_individual_ticks(device: str) -> None:
    """Validate every substep and keep RNG, telemetry and infection timing aligned."""
    runs = []
    for batched in [False, True]:
        scene = make_scene(start=(0.5, 1.0), end=(0.6, 1.0))
        scene.agent.stochasticity = 0.3
        with wp.ScopedDevice(device):
            engine = GPUSpatialQuery(scene.engine.space)
            engine.head_to_point(scene.agent, (3.5, 1.0))
            for _ in range(1 if batched else 20):
                engine.step_physics([scene.agent], batch_steps=20 if batched else 1)
        runs.append((scene.agent.location, np.concatenate(engine.telemetry)))
    assert runs[0][0] == runs[1][0]
    np.testing.assert_array_equal(runs[0][1], runs[1][1])


def test_first_safe_retry_uses_original_position(device: str) -> None:
    """The real seeded candidate sequence has an unsafe first and safe second step."""
    scene = make_scene(start=(1.8, 1.0), end=(1.9, 1.0))
    scene.agent.stochasticity = 0.8
    initial = scene.agent.location
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        engine.head_to_point(scene.agent, (2.5, 1.0))
        engine.step_physics([scene.agent])
        candidates = engine._wp_proposals.numpy()[0]  # noqa: SLF001
    actual = (scene.agent.location.x, scene.agent.location.y)
    scene.agent.location = initial
    safe = [path_allowed(scene, (float(p[0]), float(p[1]))) for p in candidates]
    assert not safe[0]
    first = safe.index(True)
    assert actual == tuple(candidates[first])


def test_changed_retry_budget_and_population_reallocate_safely(device: str) -> None:
    """Persistent buffers must follow current population and retry dimensions."""
    scene = make_scene()
    second = replace(scene.agent, idx=1, rng_generator=np.random.default_rng(42))
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        for attempts, agents in [
            (1, [scene.agent]),
            (3, [scene.agent, second]),
            (0, []),
            (0, [second]),
        ]:
            engine.max_movement_attempts = attempts
            for agent in agents:
                engine.head_to_point(agent, (2.5, 1.0))
            engine.step_physics(agents)
            assert all(agent.location.x == 1.5 for agent in agents)


@pytest.mark.parametrize(
    "field", ["movement_speed", "stochasticity", "interaction_radius"]
)
def test_negative_movement_parameters_stay_put(device: str, field: str) -> None:
    """Invalid live parameters are not a backdoor to crossing rejected walls."""
    scene = make_scene()
    initial = scene.agent.location
    setattr(scene.agent, field, -1.0)
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        engine.head_to_point(scene.agent, (2.5, 1.0))
        engine.step_physics([scene.agent])
    assert scene.agent.location == initial


def test_rejected_proposal_cannot_trigger_transmission(device: str) -> None:
    """Only accepted positions may enter the proximity kernel."""
    scene = make_scene()
    source = replace(
        scene.agent,
        idx=1,
        location=replace(scene.agent.location, x=2.5),
        infection_status=InfectionStatus.INFECTED,
        rng_generator=np.random.default_rng(42),
    )
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        engine.search_radius = 0.25
        engine.head_to_point(scene.agent, (2.5, 1.0))
        engine.head_to_point(source, (2.5, 1.0))
        engine.step_physics([scene.agent, source])
    assert scene.agent.location.x == 1.5
    assert scene.agent.infection_status == InfectionStatus.SUSCEPTIBLE
    assert not engine.transmission_events


def test_transmission_and_telemetry_match_individual_ticks(device: str) -> None:
    """A new infection becomes a source on the next tick, not after the batch."""
    runs = []
    for batched in [False, True]:
        scene = make_scene()
        agents = [
            replace(
                scene.agent,
                idx=i,
                location=replace(scene.agent.location, x=x),
                infection_status=(
                    InfectionStatus.INFECTED if i == 1 else InfectionStatus.SUSCEPTIBLE
                ),
                rng_generator=np.random.default_rng(42 + i),
            )
            for i, x in enumerate([0.6, 0.5, 0.7])
        ]
        with wp.ScopedDevice(device):
            engine = GPUSpatialQuery(scene.engine.space)
            engine.search_radius = 0.125
            for agent in agents:
                engine.head_to_point(agent, (agent.location.x, agent.location.y))
            for _ in range(1 if batched else 3):
                engine.step_physics(agents, batch_steps=3 if batched else 1)
        runs.append((engine.transmission_events, np.concatenate(engine.telemetry)))
    assert [event["time"] for event in runs[0][0]] == [1, 2]
    assert runs[0][0] == runs[1][0]
    np.testing.assert_array_equal(runs[0][1], runs[1][1])


@pytest.mark.parametrize("missing", ["floor", "unknown-floor", "building", "space"])
def test_missing_context_stays_put(device: str, missing: str) -> None:
    """Missing context cannot borrow valid geometry or corrupt staging buffers."""
    scene = make_scene(start=(0.5, 1.0), end=(1.5, 1.0))
    if missing == "space":
        scene.engine.space.clear()
    elif missing == "unknown-floor":
        scene.agent.location = replace(scene.agent.location, floor=99)
    elif missing == "floor":
        # Deliberately malformed runtime data must fail closed, not reach HashGrid.
        scene.agent.location = replace(
            scene.agent.location,
            floor=None,  # type: ignore[arg-type]
        )
    else:
        scene.agent.location = replace(scene.agent.location, building=None)
    initial = scene.agent.location
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        engine.head_to_point(scene.agent, (1.5, 1.0))
        engine.step_physics([scene.agent])
    assert scene.agent.location == initial


@pytest.mark.parametrize(
    "field",
    ["target_x", "target_y", "stochasticity", "movement_speed", "interaction_radius"],
)
@pytest.mark.parametrize("value", [nan, float("inf"), -float("inf")])
def test_nonfinite_parameters_never_reach_positions(
    device: str, field: str, value: float
) -> None:
    """Invalid proposals stay put before any proximity HashGrid sees coordinates."""
    scene = make_scene(start=(0.5, 1.0), end=(1.5, 1.0))
    initial = scene.agent.location
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        engine.head_to_point(scene.agent, (1.5, 1.0))
        setattr(scene.agent, field, value)
        engine.step_physics([scene.agent])
    assert scene.agent.location == initial


def test_invalid_position_rejected_before_advancing(device: str) -> None:
    """An invalid initial position is not relocation or a HashGrid input."""
    scene = make_scene()
    scene.agent.location = replace(scene.agent.location, x=nan)
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        with pytest.raises(SimulationModeError):
            engine.step_physics([scene.agent])
    assert engine.current_tick == 0
    assert not engine.telemetry


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("search_radius", nan),
        ("search_radius", float("inf")),
        ("search_radius", 0.0),
        ("search_radius", -1.0),
        ("max_movement_attempts", nan),
        ("max_movement_attempts", 1.5),
        ("max_movement_attempts", 2**31),
    ],
)
def test_invalid_engine_parameters_fail_before_advancing(
    device: str,
    field: str,
    value: float,
) -> None:
    """Reject unsafe live configuration before allocation, launch or telemetry."""
    scene = make_scene()
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
        setattr(engine, field, value)
        with pytest.raises(SimulationModeError):
            engine.step_physics([scene.agent])
    assert engine.current_tick == 0
    assert not engine.telemetry


def test_switching_ambient_device_is_rejected(device: str) -> None:
    """A persistent engine must not silently launch against another device's data."""
    if device == "cpu":
        pytest.skip("A second physical device is required for device-mismatch coverage")
    scene = make_scene()
    with wp.ScopedDevice(device):
        engine = GPUSpatialQuery(scene.engine.space)
    with wp.ScopedDevice("cpu"), pytest.raises(SimulationModeError):
        engine.step_physics([scene.agent])
