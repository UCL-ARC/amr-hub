"""Tests for inferred door routes, scheduling, and actual task execution."""

import math
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pytest
import warp as wp

from amr_hub_abm.agent.agent import Agent, AgentType
from amr_hub_abm.agent.kinematics import AgentKinematicsConfig, MovementStrategy
from amr_hub_abm.config import (
    LocationTimeseriesDataConfig,
    LocationTimeseriesDataFormat,
    sim_config,
)
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.location_data import read_location_timeseries
from amr_hub_abm.read_space_input import SpaceInputReader
from amr_hub_abm.simulation_factory import parse_location_timeseries
from amr_hub_abm.spatial.building import Building
from amr_hub_abm.spatial.door import Door
from amr_hub_abm.spatial.engine import SpatialQuery
from amr_hub_abm.spatial.engine_gpu import GPUSpatialQuery
from amr_hub_abm.spatial.floor import Floor
from amr_hub_abm.spatial.location import Location
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.spatial.wall import Wall
from amr_hub_abm.task.routing import plan_journey, room_graph
from amr_hub_abm.task.task import Task, TaskDoorAccess, TaskProgress


def test_staff_room_to_ward_without_recorded_doors() -> None:
    """Infer both crossings from a staff-room-to-ward location timeseries."""
    rng = np.random.default_rng(42)
    space = SpaceInputReader(Path("tests/inputs/buildings.yml"), rng)
    data = read_location_timeseries(
        LocationTimeseriesDataConfig(
            format=LocationTimeseriesDataFormat.CSV,
            path=Path("tests/inputs/location_timeseries_missing_door_events.csv"),
        )
    )
    assert data["event_type"].tolist() == ["workstation", "attend_patient"]
    agents = parse_location_timeseries(
        timeseries_data=data,
        rooms=space.rooms,
        start_time=pd.Timestamp("2024-01-01 06:55:00"),
        total_time_steps=1200,
        time_scaling_factor=1,
        rng_generator=rng,
        agent_kinematics=AgentKinematicsConfig(
            movement_speed=0.01,
            stochasticity=0.0,
            interaction_radius=0.01,
            max_movement_attempts=5,
            movement_strategy=MovementStrategy.DEADLINE_PACED,
        ),
        task_durations=sim_config.task_durations,
    )
    hcw = next(a for a in agents if a.agent_type == AgentType.HEALTHCARE_WORKER)
    engine = SpatialQuery(space.buildings)
    room = engine.get_room(hcw)
    assert room is not None
    assert room.name == "Staff Room"
    assert len(hcw.tasks) == 2
    assert not any(isinstance(task, TaskDoorAccess) for task in hcw.tasks)

    journey = plan_journey(hcw, hcw.tasks[1], engine)
    assert journey is not None
    room_names = {room.room_id: room.name for room in space.rooms}
    assert [room_names[idx] for idx in journey.room_ids] == [
        "Staff Room",
        "Corridor",
        "Ward",
    ]
    assert len(journey.crossings) == 2
    assert all(crossing.inferred for crossing in journey.crossings)


@pytest.fixture
def corridor() -> tuple[Agent, Task, SpatialQuery]:
    """Create three rectangular rooms with two open doorways."""
    rng = np.random.default_rng(42)
    doors = [
        Door(
            door_id=i,
            connecting_rooms=(10 * i, 10 * (i + 1)),
            start=(float(i), 0.4),
            end=(float(i), 0.6),
            is_open=True,
            access_control=(True, True),
        )
        for i in (1, 2)
    ]
    rooms = []
    for i in range(3):
        walls = [Wall((i, 0), (i + 1, 0)), Wall((i, 1), (i + 1, 1))]
        for x in (i, i + 1):
            if x in (1, 2):
                walls.extend([Wall((x, 0), (x, 0.4)), Wall((x, 0.6), (x, 1))])
            else:
                walls.append(Wall((x, 0), (x, 1)))
        rooms.append(
            Room(
                room_id=10 * (i + 1),
                name=f"R{i}",
                building="B",
                floor=0,
                walls=walls,
                doors=[d for d in doors if 10 * (i + 1) in d.connecting_rooms],
                contents=[],
                rng_generator=rng,
            )
        )
    floor = Floor(floor_number=0, rooms=rooms)
    engine = SpatialQuery([Building(name="B", floors=[floor])])
    agent = Agent(
        idx=1,
        location=Location(building="B", floor=0, x=0.5, y=0.5),
        heading_rad=0,
        rng_generator=rng,
        movement_speed=0.1,
        stochasticity=0,
        movement_strategy=MovementStrategy.DEADLINE_PACED,
        routing_door_duration=2,
    )
    task = Task(
        time_due=100,
        time_needed=5,
        location=Location(building="B", floor=0, x=2.5, y=0.5),
    )
    agent.tasks.append(task)
    return agent, task, engine


def test_route_and_timing(corridor: tuple[Agent, Task, SpatialQuery]) -> None:
    """Include every leg, service time, dispatch overhead, and buffer."""
    agent, task, engine = corridor
    agent.routing_buffer_steps = 3
    journey = plan_journey(agent, task, engine)
    assert journey is not None
    assert journey.room_ids == (10, 20, 30)
    door_ids: list[int] = []
    for crossing in journey.crossings:
        assert crossing.door is not None
        door_ids.append(crossing.door.door_id)
    assert door_ids == [1, 2]
    assert sum(journey.distances) == pytest.approx(2)
    assert (
        journey.travel_steps == sum(math.ceil(d / 0.1) for d in journey.distances) + 6
    )
    assert journey.departure == 95 - journey.travel_steps - 3
    first, second = journey.crossings
    assert (
        first.time_due == journey.departure + math.ceil(journey.distances[0] / 0.1) + 2
    )
    assert (
        second.time_due
        == first.time_due + 1 + math.ceil(journey.distances[1] / 0.1) + 2
    )
    assert second.time_due + 1 + math.ceil(journey.distances[2] / 0.1) + 3 == 95
    assert first.time_due < second.time_due < task.time_due
    assert list(room_graph(engine.space[0].floors[0])) == [10, 20, 30]


def test_wait_then_cross_in_order(corridor: tuple[Agent, Task, SpatialQuery]) -> None:
    """An incomplete schedule crosses doors at fixed speed and reaches its task."""
    agent, task, engine = corridor
    journey = plan_journey(agent, task, engine)
    assert journey is not None
    start = agent.location
    for time in range(journey.departure):
        agent.perform_task(time, engine)
    assert agent.location == start
    assert len(agent.tasks) == 1
    rooms = []
    for time in range(journey.departure, 120):
        agent.perform_task(time, engine)
        room = engine.get_room(agent)
        assert room is not None
        rooms.append(room.room_id)
        assert agent.movement_speed <= agent.base_movement_speed
    assert task.progress == TaskProgress.COMPLETED
    assert sorted(set(rooms)) == [10, 20, 30]
    assert len(agent.tasks) == 3
    assert all(t.inferred for t in agent.tasks[:-1])
    assert agent.tasks[-1] is task
    assert [t.time_due for t in agent.tasks] == sorted(t.time_due for t in agent.tasks)
    assert task.lateness_steps == 0


def test_late_departure(corridor: tuple[Agent, Task, SpatialQuery]) -> None:
    """Late journeys preserve observed deadlines and report actual lateness."""
    agent, task, engine = corridor
    journey = plan_journey(agent, task, engine)
    assert journey is not None
    for time in range(95, 150):
        agent.perform_task(time, engine)
    assert task.time_due == 100
    assert task.progress == TaskProgress.COMPLETED
    assert task.lateness_steps > 0
    assert [t.time_due for t in agent.tasks[:-1]] == [
        crossing.time_due for crossing in journey.crossings
    ]


def test_crossing_deadlines_before_simulation_start(
    corridor: tuple[Agent, Task, SpatialQuery],
) -> None:
    """Clamp infeasible early crossing deadlines without shifting the target."""
    agent, task, engine = corridor
    task.time_due = 5
    journey = plan_journey(agent, task, engine)
    assert journey is not None
    assert journey.departure < 0
    assert [crossing.time_due for crossing in journey.crossings] == [0, 0]
    assert task.time_due == 5


def test_recorded_door_approach(corridor: tuple[Agent, Task, SpatialQuery]) -> None:
    """Infer only the missing crossing before a recorded door event."""
    agent, _, engine = corridor
    door = engine.space[0].floors[0].rooms[1].doors[1]
    observed = TaskDoorAccess(
        time_due=100,
        time_needed=2,
        door=door,
        building="B",
        floor=0,
        destination_room=30,
    )
    journey = plan_journey(agent, observed, engine)
    assert journey is not None
    assert journey.room_ids == (10, 20)
    assert len(journey.crossings) == 1
    assert journey.target is observed
    assert not observed.inferred
    agent.location = Location(building="B", floor=0, x=1.5, y=0.5)
    assert plan_journey(agent, observed, engine) is None


def test_same_room_and_disconnected(corridor: tuple[Agent, Task, SpatialQuery]) -> None:
    """Do not add same-room crossings; reject disconnected targets."""
    agent, task, engine = corridor
    task.location = agent.location
    assert plan_journey(agent, task, engine) is None
    task.location = Location(building="B", floor=0, x=2.5, y=0.5)
    for room in engine.space[0].floors[0].rooms:
        room.doors.clear()
    with pytest.raises(SimulationModeError, match="no door route"):
        plan_journey(agent, task, engine)


def test_cross_floor(corridor: tuple[Agent, Task, SpatialQuery]) -> None:
    """Reject unsupported floor transfers before geometry lookup."""
    agent, task, engine = corridor
    task.location = Location(building="B", floor=1, x=2.5, y=0.5)
    with pytest.raises(SimulationModeError, match="across buildings or floors"):
        plan_journey(agent, task, engine)


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
def test_gpu_journey_waits_and_resumes(
    corridor: tuple[Agent, Task, SpatialQuery],
    device: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run Warp physics through departure, door service, and final arrival."""
    if device.startswith("cuda") and not wp.is_cuda_available():
        pytest.skip("CUDA device unavailable; Warp CPU execution is tested separately.")
    monkeypatch.setattr(wp.config, "kernel_cache_dir", str(tmp_path / "warp"))
    agent, task, cpu_engine = corridor
    journey = plan_journey(agent, task, cpu_engine)
    assert journey is not None
    start = agent.location
    serviced_doors: set[int] = set()
    movement_ticks = 0
    with wp.ScopedDevice(device):
        gpu_engine = GPUSpatialQuery(cpu_engine.space)
        # Both engines implement the task-facing spatial query interface.
        task_engine = cast("SpatialQuery", gpu_engine)
        for time in range(120):
            before = agent.location
            # A stale target must never move an agent during a waiting tick.
            agent.target_x, agent.target_y = 2.5, 0.5
            agent.perform_task(time, task_engine)
            assert agent.location == before  # GPU movement is deferred.
            moving = any(
                t.progress == TaskProgress.MOVING_TO_LOCATION for t in agent.tasks
            )
            for crossing in (task for task in agent.tasks if task.inferred):
                if crossing.progress == TaskProgress.IN_PROGRESS:
                    serviced_doors.add(id(crossing))
            gpu_engine.step_physics([agent])
            if not moving:
                assert agent.location.x == pytest.approx(before.x, abs=1e-6)
                assert agent.location.y == pytest.approx(before.y, abs=1e-6)
            else:
                movement_ticks += 1
                assert (
                    agent.location.distance_to(before)
                    <= agent.base_movement_speed + 1e-6
                )
            if time < journey.departure:
                assert agent.location.x == pytest.approx(start.x)
                assert agent.location.y == pytest.approx(start.y)
                assert len(agent.tasks) == 1
        assert task.progress == TaskProgress.COMPLETED
        assert len(serviced_doors) == 2
        assert movement_ticks > 0
        assert len(agent.tasks) == 3
        room = gpu_engine.get_room(agent)
        assert room is not None
        assert room.room_id == 30
