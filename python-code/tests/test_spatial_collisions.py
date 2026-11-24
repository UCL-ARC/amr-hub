"""Behavioural specifications for CPU swept-path collision safety (issue 262)."""

from dataclasses import replace
from math import cos, radians, sin
from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pytest
from shapely.geometry import LineString
from shapely.ops import unary_union

from amr_hub_abm.spatial.building import Building
from amr_hub_abm.spatial.engine import SpatialQuery
from amr_hub_abm.spatial.floor import Floor
from amr_hub_abm.spatial.wall import Wall
from tests.collision_fixtures import BUILDING, make_room, make_row_scene, make_scene

if TYPE_CHECKING:
    from amr_hub_abm.spatial.location import Location


@pytest.mark.parametrize("apply_move", [False, True], ids=["proposal", "applied"])
def test_clear_endpoint_cannot_allow_solid_wall_crossing(*, apply_move: bool) -> None:
    """MRE A: a clear destination across a solid partition must not be accepted."""
    scene = make_scene()
    start = scene.agent.location
    if apply_move:
        scene.engine.move_one_step(scene.agent)
        actual = (scene.agent.location.x, scene.agent.location.y)
    else:
        actual = scene.engine.try_move_one_step(scene.agent)
    assert actual == (start.x, start.y)
    assert scene.agent.location == start


def test_all_rejected_proposals_leave_agent_at_original_position() -> None:
    """MRE B: five wall-intersecting proposals must never become applied movement."""
    scene = make_scene(start=(1.85, 1.0), end=(2.05, 1.0))
    start = scene.agent.location
    with patch.object(
        SpatialQuery,
        "propose_new_coordinates",
        wraps=SpatialQuery.propose_new_coordinates,
    ) as propose:
        scene.engine.move_one_step(scene.agent)
    assert propose.call_count == 5
    assert scene.agent.location == start


@pytest.mark.parametrize("reverse", [False, True])
def test_doorway_crossing_is_allowed_in_both_directions(*, reverse: bool) -> None:
    """MRE C: legitimate room changes through the physical opening remain valid."""
    start, end = ((2.5, 1.0), (1.5, 1.0)) if reverse else ((1.5, 1.0), (2.5, 1.0))
    scene = make_scene(doorway=True, start=start, end=end)
    scene.engine.move_one_step(scene.agent)
    assert (scene.agent.location.x, scene.agent.location.y) == pytest.approx(end)


def test_unobstructed_step_is_not_suppressed() -> None:
    """Collision safety must not degenerate into preventing all movement."""
    scene = make_scene(start=(0.5, 1.0), end=(1.0, 1.0))
    start = scene.agent.location
    assert scene.engine.try_move_one_step(scene.agent) == pytest.approx((1.0, 1.0))
    assert scene.agent.location == start
    scene.engine.move_one_step(scene.agent)
    assert (scene.agent.location.x, scene.agent.location.y) == pytest.approx((1.0, 1.0))


@pytest.mark.parametrize("end", [(-0.5, 1.0), (4.5, 1.0)])
def test_rejected_out_of_floor_proposals_never_move_agent(
    end: tuple[float, float],
) -> None:
    """A room-lookup failure cannot become an escape from the modelled floor."""
    scene = make_scene(end=end)
    start = scene.agent.location
    scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == start


def test_retries_use_original_position_and_stop_at_first_valid_proposal() -> None:
    """Rejected coordinates neither accumulate movement nor consume extra retries."""
    scene = make_scene()
    start = scene.agent.location
    proposals = [(2.05, 1.0), (1.6, 1.0), (1.7, 1.0)]
    with patch.object(
        SpatialQuery, "propose_new_coordinates", side_effect=proposals
    ) as propose:
        actual = scene.engine.try_move_one_step(scene.agent)
    assert actual == proposals[1]
    assert scene.agent.location == start
    assert propose.call_count == 2
    assert all(call.args[0] == (start.x, start.y) for call in propose.call_args_list)


@pytest.mark.parametrize(
    ("configured", "override", "expected_calls"),
    [(5, None, 5), (0, None, 0), (5, 0, 0), (5, 1, 1), (1, 3, 3)],
)
def test_attempt_budget_and_override_are_respected(
    configured: int, override: int | None, expected_calls: int
) -> None:
    """Exhaustion returns the original coordinates, including a zero-step budget."""
    scene = make_scene()
    scene.engine.max_movement_attempts = configured
    start = scene.agent.location
    with patch.object(
        SpatialQuery, "propose_new_coordinates", return_value=(2.05, 1.0)
    ) as propose:
        actual = scene.engine.try_move_one_step(scene.agent, max_attempts=override)
    assert propose.call_count == expected_calls
    assert actual == (start.x, start.y)
    assert scene.agent.location == start


@pytest.mark.parametrize("angle", [0.0, 90.0, 45.0])
@pytest.mark.parametrize("radius", [0.0, 0.01])
@pytest.mark.parametrize("reverse", [False, True])
def test_solid_wall_blocks_all_orientations_and_directions(
    angle: float, radius: float, *, reverse: bool
) -> None:
    """Neither coordinate orientation nor zero clearance permits wall penetration."""
    start, end = ((2.5, 1.0), (1.5, 1.0)) if reverse else ((1.5, 1.0), (2.5, 1.0))
    scene = make_scene(start=start, end=end, radius=radius, angle_degrees=angle)
    initial = scene.agent.location
    scene.rooms.reverse()
    scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == initial


@pytest.mark.parametrize("angle", [0.0, 90.0, 45.0])
def test_oblique_and_horizontal_doorways_remain_passable(angle: float) -> None:
    """Rotating a valid opening must not introduce a coordinate-axis barrier."""
    scene = make_scene(doorway=True, angle_degrees=angle)
    expected = scene.engine.propose_new_coordinates(
        (scene.agent.location.x, scene.agent.location.y),
        scene.agent.heading_rad,
        scene.agent.movement_speed,
        0.0,
        scene.agent.rng_generator,
    )
    scene.engine.move_one_step(scene.agent)
    assert (scene.agent.location.x, scene.agent.location.y) == pytest.approx(expected)


@pytest.mark.parametrize("height", [0.55, 0.605])
def test_clear_endpoints_do_not_allow_clipping_door_jambs(height: float) -> None:
    """Check the physical jamb cap and clearance along the middle of the step."""
    scene = make_scene(doorway=True, start=(1.5, height), end=(2.5, height))
    initial = scene.agent.location
    scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == initial


def test_safe_clearance_past_door_jamb_is_allowed() -> None:
    """Do not block a path merely because it passes near a jamb."""
    end = (2.5, 0.625)
    scene = make_scene(doorway=True, start=(1.5, 0.625), end=end)
    scene.engine.move_one_step(scene.agent)
    assert (scene.agent.location.x, scene.agent.location.y) == pytest.approx(end)


def test_oblique_square_cap_is_not_lost_in_bounds_filter() -> None:
    """A 45-degree square cap extends beyond a half-thickness axis-aligned bound."""
    scene = make_scene(
        doorway=True,
        start=(2.5, 0.58),
        end=(2.08, 0.58),
        radius=0.0,
        angle_degrees=45.0,
    )
    initial = scene.agent.location
    scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == initial


def test_zero_clearance_still_rejects_exact_physical_wall_contact() -> None:
    """Touching the physical polygon is rejected without a clearance buffer."""
    scene = make_scene(radius=0.0)
    initial = scene.agent.location
    with patch.object(SpatialQuery, "propose_new_coordinates", return_value=(1.9, 1.0)):
        scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == initial


def test_agent_can_stop_on_doorway_threshold_and_continue() -> None:
    """A shared polygon boundary is not itself a wall inside a door opening."""
    scene = make_scene(doorway=True)
    with patch.object(
        SpatialQuery, "propose_new_coordinates", side_effect=[(2.0, 1.0), (2.5, 1.0)]
    ):
        scene.engine.move_one_step(scene.agent)
        assert (scene.agent.location.x, scene.agent.location.y) == (2.0, 1.0)
        scene.engine.move_one_step(scene.agent)
        assert (scene.agent.location.x, scene.agent.location.y) == (2.5, 1.0)


@pytest.mark.parametrize("offset", [-0.00001, 0.0, 0.00001])
def test_clearance_boundary_is_inclusive_without_relaxing_it(offset: float) -> None:
    """Binary-exact 0.25 m clearance is allowed; a closer endpoint is not."""
    end = (1.5, 0.375 + offset)
    scene = make_scene(start=(0.5, 0.5), end=end, radius=0.25)
    for room in scene.rooms:
        for wall in room.walls or []:
            wall.thickness = 0.25
    initial = scene.agent.location
    with patch.object(SpatialQuery, "propose_new_coordinates", return_value=end):
        scene.engine.move_one_step(scene.agent)
    expected = (initial.x, initial.y) if offset < 0 else end
    assert (scene.agent.location.x, scene.agent.location.y) == expected


def test_parallel_movement_at_exact_clearance_is_allowed() -> None:
    """Maintaining the clearance does not require moving away from the wall."""
    scene = make_scene(start=(0.5, 0.375), end=(1.5, 0.375), radius=0.25)
    for room in scene.rooms:
        for wall in room.walls or []:
            wall.thickness = 0.25
    scene.engine.move_one_step(scene.agent)
    assert (scene.agent.location.x, scene.agent.location.y) == (1.5, 0.375)


def test_zero_length_step_at_valid_position_is_safe() -> None:
    """Do not turn a stationary step into an invalid degenerate line geometry."""
    scene = make_scene(start=(1.5, 1.0), end=(1.5, 1.0))
    initial = scene.agent.location
    scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == initial


@pytest.mark.parametrize("all_open", [False, True])
def test_intermediate_rooms_are_checked_not_only_source_and_destination(
    *, all_open: bool
) -> None:
    """A long step may cross several openings, but not an intermediate solid wall."""
    scene = make_row_scene((True, all_open, True))
    initial = scene.agent.location
    with patch.object(SpatialQuery, "propose_new_coordinates", return_value=(7.0, 1.0)):
        scene.engine.move_one_step(scene.agent)
    expected = (7.0, 1.0) if all_open else (initial.x, initial.y)
    assert (scene.agent.location.x, scene.agent.location.y) == expected


def test_path_cannot_leave_modelled_space_and_reenter_through_openings() -> None:
    """Clear endpoints and no intervening walls do not legitimise an unmodelled gap."""
    scene = make_scene(doorway=True, end=(3.5, 1.0))
    right = scene.rooms[1]
    walls = [
        Wall((wall.start[0] + 1.0, wall.start[1]), (wall.end[0] + 1.0, wall.end[1]))
        for wall in right.walls or []
    ]
    doors = [replace(door, start=(3.0, 0.5), end=(3.0, 1.5)) for door in right.doors]
    scene.rooms[1] = make_room(walls, room_id=1, doors=doors)
    initial = scene.agent.location
    scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == initial


@pytest.mark.parametrize("other_building", [False, True])
def test_walls_in_other_spatial_context_do_not_obstruct(
    *, other_building: bool
) -> None:
    """Use the agent's building/floor context even when wall coordinates coincide."""
    scene = make_scene(start=(0.5, 1.0), end=(1.5, 1.0))
    name, level = ("Other", 0) if other_building else (BUILDING, 1)
    room = make_room(
        [
            Wall((0.9, 0.5), (1.1, 0.5)),
            Wall((1.1, 0.5), (1.1, 1.5)),
            Wall((1.1, 1.5), (0.9, 1.5)),
            Wall((0.9, 1.5), (0.9, 0.5)),
        ],
        building=name,
        floor=level,
    )
    if other_building:
        scene.engine.space.append(Building(name, [Floor(level, [room])]))
    else:
        scene.engine.space[0].floors.append(Floor(level, [room]))
    scene.engine.move_one_step(scene.agent)
    assert (scene.agent.location.x, scene.agent.location.y) == (1.5, 1.0)


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_proposals_are_rejected(coordinate: float) -> None:
    """Invalid numerical proposals must never propagate into an agent's location."""
    scene = make_scene()
    initial = scene.agent.location
    with patch.object(
        SpatialQuery, "propose_new_coordinates", return_value=(coordinate, 1.0)
    ):
        scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == initial


def test_repeated_small_steps_cannot_creep_through_wall() -> None:
    """With 1 cm steps, the agent must stop before the physical wall plus clearance."""
    scene = make_scene(start=(1.5, 1.0), end=(1.51, 1.0))
    positions = []
    for _ in range(150):
        scene.engine.move_one_step(scene.agent)
        positions.append(scene.agent.location.x)
        assert 1.5 <= scene.agent.location.x <= 1.89
        assert scene.agent.location.y == 1.0
    assert positions[-1] > 1.5
    assert len(set(positions[-30:])) == 1


def test_wall_crossing_proposal_can_be_followed_by_safe_alternative() -> None:
    """A swept-path rejection still permits a later valid proposal in this step."""
    scene = make_scene()
    with patch.object(
        SpatialQuery, "propose_new_coordinates", side_effect=[(2.5, 1.0), (1.6, 1.0)]
    ) as propose:
        scene.engine.move_one_step(scene.agent)
    assert propose.call_count == 2
    assert (scene.agent.location.x, scene.agent.location.y) == (1.6, 1.0)


@pytest.mark.parametrize("missing", ["building", "floor", "space"])
def test_missing_spatial_context_cannot_produce_movement(missing: str) -> None:
    """Do not borrow another building or floor's geometry when context is absent."""
    scene = make_scene()
    if missing == "building":
        scene.agent.location = replace(scene.agent.location, building=None)
    elif missing == "floor":
        scene.agent.location = replace(scene.agent.location, floor=10)
    else:
        scene.engine.space.clear()
    initial = scene.agent.location
    scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == initial


def test_geometry_changes_are_not_hidden_by_stale_collision_data() -> None:
    """A newly added solid boundary must affect subsequent movement proposals."""
    scene = make_scene(doorway=True)
    assert scene.engine.try_move_one_step(scene.agent) == (2.5, 1.0)
    assert scene.rooms[0].walls is not None
    scene.rooms[0].walls.append(Wall((2.0, 0.5), (2.0, 1.5)))
    assert scene.engine.try_move_one_step(scene.agent) == (1.5, 1.0)


def test_initial_wall_overlap_does_not_trigger_implicit_relocation() -> None:
    """The safety fix rejects invalid paths; it does not invent placement recovery."""
    scene = make_scene(start=(1.95, 1.0), end=(1.5, 1.0))
    initial = scene.agent.location
    scene.engine.move_one_step(scene.agent)
    assert scene.agent.location == initial


def test_seeded_stochastic_movement_is_reproducible_and_wall_safe() -> None:
    """Thread the existing RNG without global randomness or unsafe retry drift."""
    trajectories: list[list[Location]] = []
    for _ in range(2):
        scene = make_scene(start=(0.5, 1.0), end=(0.55, 1.0))
        scene.agent.stochasticity = 0.5
        trajectory = []
        for _ in range(100):
            scene.engine.move_one_step(scene.agent)
            trajectory.append(scene.agent.location)
            assert scene.agent.location.x <= 1.89
            assert 0.11 <= scene.agent.location.y <= 1.89
        trajectories.append(trajectory)
    assert trajectories[0] == trajectories[1]


@pytest.mark.parametrize("angle", [0.0, 45.0, 90.0, 135.0])
@pytest.mark.parametrize("radius", [0.0, 0.01, 0.1])
@pytest.mark.parametrize("doorway", [False, True])
def test_movement_matches_exhaustive_geometry_oracle(
    angle: float, radius: float, *, doorway: bool
) -> None:
    """Candidate filtering must agree with all-wall checks, including oblique caps."""
    rng = np.random.default_rng(262)
    theta = radians(angle)
    for _ in range(15):
        start = (float(rng.uniform(0.3, 1.7)), float(rng.uniform(0.3, 1.7)))
        end_x, end_y = rng.uniform(0.2, 3.8), rng.uniform(0.2, 1.8)
        end = (float(end_x), float(end_y))
        scene = make_scene(
            start=start, end=end, doorway=doorway, radius=radius, angle_degrees=angle
        )
        proposal = (
            end[0] * cos(theta) - end[1] * sin(theta),
            end[0] * sin(theta) + end[1] * cos(theta),
        )
        initial = (scene.agent.location.x, scene.agent.location.y)
        path = LineString([initial, proposal])
        allowed = unary_union([room.region for room in scene.rooms]).covers(path)
        for room in scene.rooms:
            for wall in room.walls or []:
                polygon = wall.polygon
                if path.intersects(polygon) or path.distance(polygon) < radius:
                    allowed = False
        with patch.object(
            SpatialQuery, "propose_new_coordinates", return_value=proposal
        ):
            actual = scene.engine.try_move_one_step(scene.agent)
        assert actual == (proposal if allowed else initial)
