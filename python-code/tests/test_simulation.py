"""Test for the Simulation class in amr_hub_abm.simulation module."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from amr_hub_abm.agent.agent import Agent, AgentType, InfectionStatus
from amr_hub_abm.agent.internal_state import InternalState, InternalStateConfig
from amr_hub_abm.agent.needs_policy import Need, NeedRule, NeedsPolicy
from amr_hub_abm.exceptions import TimeError
from amr_hub_abm.simulation import Simulation, SimulationMode
from amr_hub_abm.spatial.building import Building
from amr_hub_abm.spatial.door import Door
from amr_hub_abm.spatial.engine import SpatialQuery
from amr_hub_abm.spatial.floor import Floor
from amr_hub_abm.spatial.furniture import Content, ContentType
from amr_hub_abm.spatial.location import Location
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.spatial.wall import Wall
from amr_hub_abm.task.task import Task, TaskOccupyContent, TaskProgress, TaskSource
from amr_hub_abm.task.task_need import TaskNeed


@pytest.fixture
def sample_door() -> Door:
    """Create a sample Door for testing."""
    return Door(
        is_open=True,
        connecting_rooms=(0, 1),
        access_control=(True, True),
        start=(5.0, 1.0),
        end=(5.0, 2.0),
        door_id=0,
    )


@pytest.fixture
def sample_rooms(sample_door: Door) -> list[Room]:
    """Create two adjacent rooms sharing a door on floor 0."""
    room1 = Room(
        room_id=0,
        name="Room1",
        building="TestBuilding",
        floor=0,
        contents=[],
        doors=[sample_door],
        walls=[
            Wall(start=(0.0, 0.0), end=(0.0, 5.0)),
            Wall(start=(0.0, 5.0), end=(5.0, 5.0)),
            Wall(start=(5.0, 5.0), end=(5.0, 2.0)),
            Wall(start=(5.0, 1.0), end=(5.0, 0.0)),
            Wall(start=(5.0, 0.0), end=(0.0, 0.0)),
        ],
        rng_generator=np.random.default_rng(),
    )
    room2 = Room(
        room_id=1,
        name="Room2",
        building="TestBuilding",
        floor=0,
        contents=[],
        doors=[sample_door],
        walls=[
            Wall(start=(5.0, 2.0), end=(5.0, 5.0)),
            Wall(start=(5.0, 5.0), end=(10.0, 5.0)),
            Wall(start=(10.0, 5.0), end=(10.0, 0.0)),
            Wall(start=(10.0, 0.0), end=(5.0, 0.0)),
            Wall(start=(5.0, 0.0), end=(5.0, 2.0)),
        ],
        rng_generator=np.random.default_rng(),
    )
    return [room1, room2]


@pytest.fixture
def sample_floor(sample_rooms: list[Room]) -> Floor:
    """Floor 0 — matches rooms and agent."""
    return Floor(floor_number=0, rooms=sample_rooms)


@pytest.fixture
def sample_building(sample_floor: Floor) -> Building:
    """Create a sample Building for testing."""
    return Building(name="TestBuilding", floors=[sample_floor])


@pytest.fixture
def sample_agent() -> Agent:
    """Agent at (0.5, 0.5) on floor 0 of TestBuilding."""
    return Agent(
        idx=1,
        agent_type=AgentType.PATIENT,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(x=0.5, y=0.5, floor=0, building="TestBuilding"),
        heading_rad=0.0,
        rng_generator=np.random.default_rng(42),
    )


@pytest.fixture
def sample_simulation(sample_building: Building, sample_agent: Agent) -> Simulation:
    """Create a sample Simulation for testing."""
    return Simulation(
        name="TestSimulation",
        description="A test simulation.",
        total_simulation_time=10,
        mode=SimulationMode.TOPOLOGICAL,
        space=[sample_building],
        agents=[sample_agent],
        rng_generator=np.random.default_rng(42),
    )


def test_simulation_initialization(sample_simulation: Simulation) -> None:
    """Test the initialization of the Simulation class."""
    assert sample_simulation.mode == SimulationMode.TOPOLOGICAL
    assert sample_simulation.total_simulation_time == 10
    assert sample_simulation.time == 0
    assert sample_simulation.name == "TestSimulation"
    assert sample_simulation.description == "A test simulation."
    assert len(sample_simulation.space) == 1
    assert sample_simulation.space[0].name == "TestBuilding"
    assert len(sample_simulation.agents) == 1
    assert sample_simulation.agents[0].idx == 1


def test_simulation_step_advances_time(sample_simulation: Simulation) -> None:
    """Test that the simulation step method advances time correctly."""
    assert sample_simulation.time == 0
    sample_simulation.step()
    assert sample_simulation.time == 1


def test_simulation_step_updates_internal_state(sample_simulation: Simulation) -> None:
    """Simulation steps advance configured internal needs."""
    sample_simulation.internal_state_config = InternalStateConfig(
        hcw_initial_fatigue=0.0,
        hcw_initial_hunger=0.0,
        hcw_initial_toilet_need=0.0,
        patient_initial_hunger=0.0,
        patient_initial_toilet_need=0.0,
        hcw_fatigue_rate=0.1,
        hcw_hunger_rate=0.2,
        hcw_toilet_rate=0.3,
        patient_hunger_rate=0.4,
        patient_toilet_rate=0.5,
    )

    sample_simulation.step()

    assert sample_simulation.agents[0].internal_state == InternalState(
        fatigue=None, hunger=0.4, toilet_need=0.5
    )


@pytest.fixture
def needs_simulation(sample_building: Building, sample_agent: Agent) -> Simulation:
    """Create an opt-in HCW simulation with an available chair."""
    room = sample_building.floors[0].rooms[0]
    room.contents.append(
        Content(content_type=ContentType.CHAIR, location=sample_agent.location)
    )
    sample_agent.agent_type = AgentType.HEALTHCARE_WORKER
    sample_agent.internal_state = InternalState(fatigue=0.0)
    rule = NeedRule(threshold=0.5, urgent_threshold=0.9, duration=2, priority=10)
    return Simulation(
        name="Needs test",
        description="Synthetic needs test",
        mode=SimulationMode.SPATIAL,
        space=[sample_building],
        agents=[sample_agent],
        total_simulation_time=12,
        rng_generator=np.random.default_rng(42),
        needs_policy=NeedsPolicy(
            fatigue=rule,
            hunger=rule,
            toilet_need=rule,
            eating_building="TestBuilding",
            eating_floor=0,
            eating_room="Room1",
            travel_timeout=3,
            retry_interval=2,
        ),
    )


def test_urgent_need_suspends_and_resumes_recorded_work(
    needs_simulation: Simulation,
) -> None:
    """An urgent need is satisfied before recorded work resumes with progress."""
    agent = needs_simulation.agents[0]
    data_task = Task(
        time_needed=5,
        time_due=5,
        location=agent.location,
        source=TaskSource.LOCATION_DATA,
    )
    agent.tasks.append(data_task)
    needs_simulation.step()
    assert data_task.progress == TaskProgress.IN_PROGRESS

    agent.internal_state.fatigue = 0.9
    needs_simulation.step()
    need_task = next(task for task in agent.tasks if isinstance(task, TaskNeed))
    assert data_task.progress == TaskProgress.SUSPENDED
    assert data_task.time_spent(1) == 1
    assert agent.internal_state.fatigue == 0.9
    needs_simulation.step()
    assert len([task for task in agent.tasks if isinstance(task, TaskNeed)]) == 1
    needs_simulation.step()
    assert need_task.progress == TaskProgress.COMPLETED
    assert need_task not in agent.tasks
    assert agent.internal_state.fatigue == 0.0
    needs_simulation.step()
    assert data_task.progress == TaskProgress.IN_PROGRESS
    for _ in range(4):
        needs_simulation.step()
    assert data_task.progress == TaskProgress.COMPLETED
    assert data_task.time_spent(needs_simulation.time) == 5


def test_nonurgent_need_waits_for_due_data(needs_simulation: Simulation) -> None:
    """Due recorded work takes precedence over a non-urgent need."""
    agent = needs_simulation.agents[0]
    agent.internal_state.fatigue = 0.5
    task = Task(
        time_needed=3,
        time_due=3,
        location=agent.location,
        source=TaskSource.LOCATION_DATA,
    )
    agent.tasks.append(task)
    needs_simulation.step()
    assert task.progress == TaskProgress.IN_PROGRESS
    assert not any(isinstance(candidate, TaskNeed) for candidate in agent.tasks)


def test_due_data_interrupts_nonurgent_need_travel(
    needs_simulation: Simulation,
) -> None:
    """Newly due recorded work interrupts non-urgent autonomous travel."""
    agent = needs_simulation.agents[0]
    agent.internal_state.fatigue = 0.5
    needs_simulation.rooms[0].contents[0].location = Location(
        building="TestBuilding", floor=0, x=2.0, y=2.0
    )
    assert needs_simulation.needs_policy is not None
    needs_simulation.needs_policy = replace(
        needs_simulation.needs_policy, travel_timeout=20
    )
    task = Task(
        time_needed=1,
        time_due=4,
        location=agent.location,
        source=TaskSource.LOCATION_DATA,
    )
    agent.tasks.append(task)
    for _ in range(4):
        needs_simulation.step()
    need = next(
        candidate for candidate in agent.tasks if isinstance(candidate, TaskNeed)
    )
    assert need.progress == TaskProgress.SUSPENDED
    assert task.progress == TaskProgress.IN_PROGRESS
    assert agent.internal_state.fatigue == 0.5
    needs_simulation.step()
    assert task.progress == TaskProgress.COMPLETED
    needs_simulation.step()
    assert need.progress == TaskProgress.MOVING_TO_LOCATION


def test_suspended_need_can_become_urgent_and_interrupt_data(
    needs_simulation: Simulation,
) -> None:
    """A pending need that becomes urgent may preempt recorded work."""
    agent = needs_simulation.agents[0]
    agent.internal_state.fatigue = 0.5
    needs_simulation.rooms[0].contents[0].location = Location(
        building="TestBuilding", floor=0, x=2.0, y=2.0
    )
    assert needs_simulation.needs_policy is not None
    needs_simulation.needs_policy = replace(
        needs_simulation.needs_policy, travel_timeout=20
    )
    task = Task(
        time_needed=3,
        time_due=6,
        location=agent.location,
        source=TaskSource.LOCATION_DATA,
    )
    agent.tasks.append(task)
    for _ in range(4):
        needs_simulation.step()
    need = next(
        candidate for candidate in agent.tasks if isinstance(candidate, TaskNeed)
    )
    assert need.progress == TaskProgress.SUSPENDED
    assert task.progress == TaskProgress.IN_PROGRESS
    agent.internal_state.fatigue = 0.9
    needs_simulation.step()
    assert need.progress == TaskProgress.MOVING_TO_LOCATION
    assert task.progress == TaskProgress.SUSPENDED


@pytest.mark.parametrize("need", [Need.HUNGER, Need.TOILET])
def test_hunger_and_toilet_need_use_configured_facilities(
    needs_simulation: Simulation, need: Need
) -> None:
    """Meals and toilet breaks reset their own needs after facility use."""
    agent = needs_simulation.agents[0]
    setattr(agent.internal_state, need.value, 0.9)
    if need == Need.TOILET:
        needs_simulation.rooms[0].contents.append(
            Content(content_type=ContentType.TOILET, location=agent.location)
        )
    needs_simulation.step()
    task = next(task for task in agent.tasks if isinstance(task, TaskNeed))
    needs_simulation.step()
    needs_simulation.step()
    assert task.need == need
    assert task.progress == TaskProgress.COMPLETED
    assert getattr(agent.internal_state, need.value) == 0.0


def test_rest_can_use_agent_owned_chair(needs_simulation: Simulation) -> None:
    """An agent already seated can use its own chair to rest."""
    agent = needs_simulation.agents[0]
    chair = needs_simulation.rooms[0].contents[0]
    assert chair.try_occupy((agent.idx, agent.agent_type))
    agent.stationary = True
    agent.internal_state.fatigue = 0.9
    for _ in range(3):
        needs_simulation.step()
    assert agent.internal_state.fatigue == 0.0
    assert chair.available


def test_workers_take_turns_at_contested_facility(needs_simulation: Simulation) -> None:
    """Two HCWs cannot use the same chair concurrently and both can retry."""
    first = needs_simulation.agents[0]
    first.internal_state.fatigue = 0.9
    second = Agent(
        idx=2,
        agent_type=AgentType.HEALTHCARE_WORKER,
        location=first.location,
        heading_rad=0,
        rng_generator=np.random.default_rng(42),
        internal_state=InternalState(fatigue=0.9),
        retry_data_tasks=True,
    )
    needs_simulation.agents.append(second)
    for _ in range(8):
        needs_simulation.step()
    assert first.internal_state.fatigue == 0
    assert second.internal_state.fatigue == 0
    assert needs_simulation.rooms[0].contents[0].available


def test_patient_needs_do_not_schedule_hcw_activities(
    needs_simulation: Simulation,
) -> None:
    """The policy leaves patient behavior unchanged."""
    patient = Agent(
        idx=2,
        agent_type=AgentType.PATIENT,
        location=needs_simulation.agents[0].location,
        heading_rad=0,
        rng_generator=np.random.default_rng(42),
        internal_state=InternalState(hunger=0.9),
    )
    needs_simulation.agents.append(patient)
    needs_simulation.step()
    assert not patient.tasks
    assert patient.internal_state.hunger == 0.9


def test_travel_timeout_releases_facility_and_resumes_data(
    needs_simulation: Simulation, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed need trip cannot repeatedly starve its interrupted data task."""
    agent = needs_simulation.agents[0]
    room = needs_simulation.rooms[0]
    room.contents[0].location = Location(building="TestBuilding", floor=0, x=2.0, y=2.0)
    data_task = Task(
        time_needed=5,
        time_due=5,
        location=agent.location,
        source=TaskSource.LOCATION_DATA,
    )
    agent.tasks.append(data_task)
    needs_simulation.step()
    agent.internal_state.fatigue = 0.9
    for _ in range(8):
        needs_simulation.step()
    assert data_task.progress == TaskProgress.COMPLETED
    assert agent.internal_state.fatigue == 0.9
    assert "could not reach" in caplog.text
    assert room.contents[0].available


def test_blocked_route_does_not_interrupt(
    needs_simulation: Simulation, caplog: pytest.LogCaptureFixture
) -> None:
    """A facility with no clear direct or doorway route does not interrupt work."""
    assert needs_simulation.needs_policy is not None
    needs_simulation.needs_policy = replace(
        needs_simulation.needs_policy, eating_room="Room2"
    )
    needs_simulation.rooms[0].doors.clear()
    room = needs_simulation.rooms[1]
    room.contents.append(
        Content(
            content_type=ContentType.CHAIR,
            location=Location(building="TestBuilding", floor=0, x=9.0, y=4.0),
        )
    )
    agent = needs_simulation.agents[0]
    task = Task(
        time_needed=3,
        time_due=3,
        location=agent.location,
        source=TaskSource.LOCATION_DATA,
    )
    agent.tasks.append(task)
    needs_simulation.step()
    agent.internal_state.hunger = 0.9
    needs_simulation.step()
    assert task.progress == TaskProgress.IN_PROGRESS
    assert "no available reachable" in caplog.text


def test_unavailable_need_facility_does_not_interrupt(
    needs_simulation: Simulation, caplog: pytest.LogCaptureFixture
) -> None:
    """A blocked facility leaves the current recorded task active."""
    agent = needs_simulation.agents[0]
    chair = needs_simulation.rooms[0].contents[0]
    assert chair.try_reserve((999, AgentType.HEALTHCARE_WORKER))
    task = Task(
        time_needed=3,
        time_due=3,
        location=agent.location,
        source=TaskSource.LOCATION_DATA,
    )
    agent.tasks.append(task)
    needs_simulation.step()
    agent.internal_state.fatigue = 0.9
    needs_simulation.step()
    assert task.progress == TaskProgress.IN_PROGRESS
    assert agent.internal_state.fatigue == 0.9
    assert "no available reachable" in caplog.text


def test_unavailable_recorded_task_is_retained_when_policy_enabled(
    needs_simulation: Simulation,
) -> None:
    """Unavailable content for recorded work is retried, not discarded."""
    agent = needs_simulation.agents[0]
    room = needs_simulation.rooms[0]
    chair = room.contents[0]
    assert chair.try_reserve((999, AgentType.HEALTHCARE_WORKER))
    task = TaskOccupyContent(
        time_needed=1,
        time_due=1,
        room=room,
        content_type=ContentType.CHAIR,
        source=TaskSource.LOCATION_DATA,
    )
    agent.tasks.append(task)
    needs_simulation.step()
    assert task in agent.tasks
    assert task.progress == TaskProgress.NOT_STARTED
    assert chair.release_reservation((999, AgentType.HEALTHCARE_WORKER))
    needs_simulation.step()
    assert task.progress == TaskProgress.IN_PROGRESS


def test_unfinished_recorded_task_is_reported_at_end(
    needs_simulation: Simulation, caplog: pytest.LogCaptureFixture
) -> None:
    """A finished run reports data work that could not be completed."""
    agent = needs_simulation.agents[0]
    agent.tasks.append(
        Task(
            time_needed=20,
            time_due=20,
            location=agent.location,
            source=TaskSource.LOCATION_DATA,
        )
    )
    for _ in range(needs_simulation.total_simulation_time):
        needs_simulation.step()
    assert "unfinished recorded task" in caplog.text
    assert needs_simulation.time == needs_simulation.total_simulation_time


def test_gpu_need_movement_and_completion(needs_simulation: Simulation) -> None:
    """Exercise opt-in need movement through the real GPU physics path."""
    import warp as wp  # noqa: PLC0415

    if not wp.is_cuda_available():
        pytest.skip("CUDA device is not available")
    agent = needs_simulation.agents[0]
    agent.internal_state.fatigue = 0.9
    agent.stochasticity = 0.0
    agent.movement_speed = 0.3
    agent.base_movement_speed = 0.3
    needs_simulation.rooms[0].contents[0].location = Location(
        building="TestBuilding", floor=0, x=1.1, y=0.5
    )
    assert needs_simulation.needs_policy is not None
    needs_simulation.needs_policy = replace(
        needs_simulation.needs_policy, travel_timeout=10
    )
    gpu_simulation = replace(needs_simulation, use_gpu=True)
    gpu_simulation.step()
    task = next(task for task in agent.tasks if isinstance(task, TaskNeed))
    for _ in range(7):
        gpu_simulation.step()
    assert task.progress == TaskProgress.COMPLETED
    assert agent.internal_state.fatigue == 0.0
    assert agent.location.x == pytest.approx(1.1, abs=0.02)


def test_simulation_excessive_current_time_raises(
    sample_simulation: Simulation,
) -> None:
    """Test that stepping past total_simulation_time raises TimeError."""
    sample_simulation.time = sample_simulation.total_simulation_time + 1  # type: ignore[assignment]

    with pytest.raises(TimeError):
        sample_simulation.step()


def test_agent_get_room(
    sample_agent: Agent,
    sample_building: Building,
) -> None:
    """Test that the spatial engine can find the agent's room."""
    engine = SpatialQuery(space=[sample_building])
    room = engine.get_room(sample_agent)

    assert room is not None
    assert room.name == "Room1"


def test_agent_get_room_wrong_building(
    sample_agent: Agent,
    sample_building: Building,
) -> None:
    """Agent in a different building returns None."""
    sample_agent.location = Location(x=0.5, y=0.5, floor=0, building="OtherBuilding")
    engine = SpatialQuery(space=[sample_building])
    assert engine.get_room(sample_agent) is None


def test_agent_get_room_no_building(
    sample_agent: Agent,
    sample_building: Building,
) -> None:
    """Agent with building=None returns None."""
    sample_agent.location = Location(x=0.5, y=0.5, floor=0, building=None)
    engine = SpatialQuery(space=[sample_building])
    assert engine.get_room(sample_agent) is None


def test_simulation_repr(sample_simulation: Simulation) -> None:
    """Test that the simulation __repr__ returns expected content."""
    repr_str = repr(sample_simulation)

    assert "Simulation: TestSimulation" in repr_str
    assert "Description: A test simulation." in repr_str
    assert "Mode: 1" in repr_str
    assert "Total Simulation Time: 10" in repr_str
    assert "Current Time: 0" in repr_str
    assert "Number of Buildings: 1" in repr_str
    assert "Number of Agents: 1" in repr_str


def test_plot_current_state(
    sample_simulation: Simulation,
    tmp_path: Path,
) -> None:
    """Test that plot_current_state creates output files."""
    sample_simulation.plot_current_state(tmp_path)

    expected_file = tmp_path / "TestBuilding_time_0.png"
    assert expected_file.exists()


def test_plot_current_state_raises_on_file_path(
    sample_simulation: Simulation,
    tmp_path: Path,
) -> None:
    """Test that plot_current_state raises error when given a file path."""
    file_path = tmp_path / "test.txt"

    with pytest.raises(NotADirectoryError, match="is not a directory"):
        sample_simulation.plot_current_state(file_path)
