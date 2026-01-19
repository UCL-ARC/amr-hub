from pathlib import Path
import time

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
    print("Simulation created successfully.")

    # tasks = simulation.agents[0].tasks

    # for task in tasks:
    #     print(task.progress)

    while simulation.time < 10:
        # while simulation.time < simulation.total_simulation_time:
        simulation.step()
        print(f"Simulation time: {simulation.time}")
        # agent = simulation.agents[0]
        # tasks = agent.tasks
        # for task in tasks:
        #     print(
        #         f"Task Type: {task.task_type}, Progress: {task.progress}, Current Time: {simulation.time}, Time Due: {task.time_due}"
        #     )


if __name__ == "__main__":
    time_start = time.time()
    simulate()
    time_end = time.time()
    print(f"Simulation run time: {time_end - time_start} seconds")
