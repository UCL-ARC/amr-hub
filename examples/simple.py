from pathlib import Path
import time

from amr_hub_abm.simulation_factory import create_simulation


def simulate():
    config_path = Path("tests/inputs/simulation_config.yml")
    simulation = create_simulation(config_path)
    print("Simulation created successfully...")

    while simulation.time < simulation.total_simulation_time:
        simulation.step()


if __name__ == "__main__":
    time_start = time.time()
    simulate()
    time_end = time.time()
    print(f"Simulation run time: {time_end - time_start} seconds")
