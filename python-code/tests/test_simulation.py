"""Test for the Simulation class in amr_hub_abm.simulation module."""

from pathlib import Path

import pytest

from amr_hub_abm.agent import Agent, AgentType, InfectionStatus
from amr_hub_abm.exceptions import TimeError
from amr_hub_abm.simulation import Simulation, SimulationMode
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall


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
    """Create a sample Room for testing."""
    room1 = Room(
        room_id=0,
        name="Room1",
        building="TestBuilding",
        floor=1,
        contents=[],
        doors=[sample_door],
        walls=[
            Wall(start=(0.0, 0.0), end=(0.0, 5.0)),
            Wall(start=(0.0, 5.0), end=(5.0, 5.0)),
            Wall(start=(5.0, 5.0), end=(5.0, 2.0)),
            Wall(start=(5.0, 1.0), end=(5.0, 0.0)),
            Wall(start=(5.0, 0.0), end=(0.0, 0.0)),
        ],
    )
    room2 = Room(
        room_id=1,
        name="Room2",
        building="TestBuilding",
        floor=1,
        contents=[],
        doors=[sample_door],
        walls=[
            Wall(start=(5.0, 2.0), end=(5.0, 5.0)),
            Wall(start=(5.0, 5.0), end=(10.0, 5.0)),
            Wall(start=(10.0, 5.0), end=(10.0, 0.0)),
            Wall(start=(10.0, 0.0), end=(5.0, 0.0)),
            Wall(start=(5.0, 0.0), end=(5.0, 2.0)),
        ],
    )
    return [room1, room2]


@pytest.fixture
def sample_floor(sample_rooms: list[Room]) -> Floor:
    """Create a sample Floor for testing."""
    return Floor(floor_number=0, rooms=sample_rooms)


@pytest.fixture
def sample_building(sample_floor: Floor) -> Building:
    """Create a sample Building for testing."""
    return Building(name="TestBuilding", floors=[sample_floor])


@pytest.fixture
def sample_agent(sample_building: Building) -> Agent:
    """Create a sample Agent for testing."""
    return Agent(
        idx=1,
        agent_type=AgentType.PATIENT,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(
            x=0.5,
            y=0.5,
            floor=0,
            building=sample_building.name,
        ),
        heading=0.0,
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
    )


def test_simulation_initialization(
    sample_simulation: Simulation,
) -> None:
    """Test the initialization of the Simulation class."""
    simulation = sample_simulation

    assert simulation.mode == SimulationMode.TOPOLOGICAL
    assert simulation.total_simulation_time == 10
    assert simulation.time == 0
    assert simulation.name == "TestSimulation"
    assert simulation.description == "A test simulation."
    assert len(simulation.space) == 1
    assert simulation.space[0].name == "TestBuilding"
    assert len(simulation.agents) == 1
    assert simulation.agents[0].idx == 1


def test_simulation_step_advances_time(
    sample_simulation: Simulation,
) -> None:
    """Test that the simulation step method advances time correctly."""
    simulation = sample_simulation
    initial_time = simulation.time

    simulation.step()

    assert simulation.time == initial_time + 1


def test_simulation_excessive_current_time_raises(
    sample_simulation: Simulation,
) -> None:
    """Test that negative current time raises a ValueError."""
    simulation = sample_simulation
    simulation.time = sample_simulation.total_simulation_time + 1  # type: ignore[assignment]

    with pytest.raises(TimeError) as excinfo:
        simulation.step()
    assert "Invalid time value encountered" in str(excinfo.value)


def test_agent_get_room(
    sample_simulation: Simulation,
    sample_agent: Agent,
) -> None:
    """Test that the agent can get its current room."""
    simulation = sample_simulation
    agent = sample_agent

    room = agent.get_room(simulation.space)

    assert room is not None
    assert room.name == "Room1"


def test_agent_get_room_in_multiple_buildings(
    sample_agent: Agent,
    sample_building: Building,
) -> None:
    """Test that the agent can get its current room in multiple buildings."""
    building1 = Building(name="Building1", floors=[])

    building2 = Building(name="Building2", floors=[Floor(floor_number=3, rooms=[])])
    building3 = sample_building

    simulation_space = [building1, building2, building3]

    room = sample_agent.get_room(simulation_space)

    assert room == sample_building.floors[0].rooms[0]


def test_agent_get_room_no_floors(
    sample_agent: Agent,
) -> None:
    """Test that the agent returns None when building has no floors."""
    simulation_space = [
        Building(name="BuildingX", floors=[]),
        Building(name="BuildingY", floors=[Floor(floor_number=0, rooms=[])]),
        Building(
            name="TestBuilding",
            floors=[],
        ),
    ]

    room = sample_agent.get_room(simulation_space)

    assert room is None


def test_agent_get_room_no_matching_floor(
    sample_agent: Agent,
) -> None:
    """Test that the agent returns None when no matching floor is found."""
    simulation_space = [
        Building(
            name="TestBuilding",
            floors=[Floor(floor_number=2, rooms=[])],
        ),
    ]

    room = sample_agent.get_room(simulation_space)

    assert room is None


def test_agent_get_room_no_matching_building(
    sample_agent: Agent,
) -> None:
    """Test that the agent returns None when no matching building is found."""
    simulation_space = [
        Building(name="BuildingA", floors=[]),
        Building(name="BuildingB", floors=[Floor(floor_number=0, rooms=[])]),
    ]

    room = sample_agent.get_room(simulation_space)

    assert room is None


def test_agent_get_room_no_buildings(
    sample_agent: Agent,
) -> None:
    """Test that the agent returns None when there are no buildings."""
    simulation_space: list[Building] = []

    room = sample_agent.get_room(simulation_space)

    assert room is None


def test_agent_get_room_no_rooms(
    sample_agent: Agent,
) -> None:
    """Test that the agent returns None when floor has no rooms."""
    simulation_space = [
        Building(
            name="TestBuilding",
            floors=[Floor(floor_number=0, rooms=[])],
        ),
    ]

    room = sample_agent.get_room(simulation_space)

    assert room is None


def test_agent_get_room_not_found(
    sample_agent: Agent,
) -> None:
    """Test that the agent returns None when not in any room."""
    simulation_space = [
        Building(name="BuildingX", floors=[]),
        Building(name="BuildingY", floors=[Floor(floor_number=0, rooms=[])]),
    ]

    room = sample_agent.get_room(simulation_space)

    assert room is None


def test_simulation_repr(
    sample_simulation: Simulation,
) -> None:
    """Test that the simulation __repr__ method returns correct string."""
    simulation = sample_simulation

    repr_str = repr(simulation)

    assert "Simulation: TestSimulation" in repr_str
    assert "Description: A test simulation." in repr_str
    assert "Mode: topological" in repr_str
    assert "Total Simulation Time: 10" in repr_str
    assert "Current Time: 0" in repr_str
    assert "Number of Buildings: 1" in repr_str
    assert "Number of Agents: 1" in repr_str


def test_plot_current_state(
    sample_simulation: Simulation,
    tmp_path: Path,
) -> None:
    """Test that the plot_current_state method creates output files."""
    simulation = sample_simulation

    simulation.plot_current_state(tmp_path)

    expected_file = tmp_path / "plot_TestSimulation_building_TestBuilding_time_0.png"
    assert expected_file.exists()


def test_plot_current_state_raises_on_file_path(
    sample_simulation: Simulation,
    tmp_path: Path,
) -> None:
    """Test that plot_current_state raises error when given a file path."""
    simulation = sample_simulation
    file_path = tmp_path / "test.txt"

    with pytest.raises(NotADirectoryError) as excinfo:
        simulation.plot_current_state(file_path)
    assert "is not a directory" in str(excinfo.value)
