"""Test for the Simulation class in amr_hub_abm.simulation module."""

from pathlib import Path

import numpy as np
import pytest

from amr_hub_abm.agent.agent import Agent, AgentType, InfectionStatus
from amr_hub_abm.exceptions import TimeError
from amr_hub_abm.simulation import Simulation, SimulationMode
from amr_hub_abm.spatial.building import Building
from amr_hub_abm.spatial.door import Door
from amr_hub_abm.spatial.engine import SpatialQuery
from amr_hub_abm.spatial.floor import Floor
from amr_hub_abm.spatial.location import Location
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.spatial.wall import Wall


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
