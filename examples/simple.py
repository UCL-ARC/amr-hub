from pathlib import Path

from amr_hub_abm.agent import Agent, AgentType, InfectionStatus
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.location import Location
from amr_hub_abm.simulation_factory import create_simulation


def create_sample_agent() -> Agent:
    """Create a sample agent for demonstration purposes."""
    building = Building(name="Sample Building", floors=[])
    location = Location(x=10.0, y=20.0, building=building.name, floor=1)

    agent = Agent(
        idx=1,
        location=location,
        heading=90.0,
        agent_type=AgentType.HEALTHCARE_WORKER,
        infection_status=InfectionStatus.SUSCEPTIBLE,
    )

    return agent


def simulate():
    config_path = Path("tests/inputs/simulation_config.yml")
    simulation = create_simulation(config_path)
    print(simulation)
    simulation.plot_current_state()
    print("Simulation created successfully.")


if __name__ == "__main__":
    simulate()
