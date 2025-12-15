"""Test for the Simulation class in amr_hub_abm.simulation module."""

import pytest

from amr_hub_abm.agent import Agent, AgentType, InfectionStatus
from amr_hub_abm.exceptions import TimeError
from amr_hub_abm.simulation import Simulation, SimulationMode
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room


@pytest.fixture
def sample_door() -> Door:
    """Create a sample Door for testing."""
    return Door(
        door_id=1,
        open=True,
        connecting_rooms=(0, 1),
        access_control=(True, True),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
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
        area=20.0,
    )
    room2 = Room(
        room_id=1,
        name="Room2",
        building="TestBuilding",
        floor=1,
        contents=[],
        doors=[sample_door],
        area=30.0,
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
    assert simulation.total_simulation_time == 10  # noqa: PLR2004
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
