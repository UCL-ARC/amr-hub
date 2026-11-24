"""Task-level movement must preserve CPU collision safety, not force progress."""

import pytest
from shapely.geometry import LineString

from amr_hub_abm.agent.kinematics import MovementStrategy
from amr_hub_abm.spatial.location import Location
from amr_hub_abm.task.task import Task, TaskDoorAccess, TaskProgress, TaskType
from tests.collision_fixtures import BUILDING, make_scene


@pytest.mark.parametrize("strategy", list(MovementStrategy))
def test_door_access_task_completes_without_solid_wall_crossings(
    strategy: MovementStrategy,
) -> None:
    """Real door-task dispatch and movement can reach the destination room safely."""
    scene = make_scene(doorway=True, start=(1.5, 1.0), end=(1.55, 1.0))
    scene.agent.movement_strategy = strategy
    task = TaskDoorAccess(
        door=scene.rooms[0].doors[0],
        building=BUILDING,
        floor=0,
        destination_room=1,
        time_needed=2,
        time_due=14,
    )
    for time in range(50):
        previous = scene.agent.location
        task.update_progress(time, scene.agent, scene.engine)
        current = scene.agent.location
        if current != previous:
            path = LineString([(previous.x, previous.y), (current.x, current.y)])
            for room in scene.rooms:
                for wall in room.walls or []:
                    assert not path.intersects(wall.polygon)
                    assert path.distance(wall.polygon) >= scene.agent.interaction_radius
        if task.progress == TaskProgress.COMPLETED:
            break
    assert task.progress == TaskProgress.COMPLETED
    assert scene.agent.location.x > 2.0
    assert scene.engine.get_room(scene.agent) is scene.rooms[1]


@pytest.mark.parametrize("strategy", list(MovementStrategy))
def test_blocked_task_does_not_cross_wall_or_falsely_complete(
    strategy: MovementStrategy,
) -> None:
    """A missing doorway route may stall a task, even when its deadline passes."""
    scene = make_scene(start=(1.5, 1.0), end=(1.55, 1.0))
    scene.agent.movement_strategy = strategy
    task = Task(
        task_type=TaskType.GOTO_LOCATION,
        location=Location(x=2.5, y=1.0, floor=0, building=BUILDING),
        time_needed=1,
        time_due=2,
    )
    for time in range(80):
        task.update_progress(time, scene.agent, scene.engine)
        assert scene.agent.location.x <= 1.89
    assert task.progress == TaskProgress.MOVING_TO_LOCATION
    assert task.time_started is None
    assert task.time_completed is None
