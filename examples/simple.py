from pathlib import Path
import time

from amr_hub_abm.simulation_factory import create_simulation


def simulate(plot: bool = False, record: bool = False) -> None:
    config_path = Path("tests/inputs/simulation_config.yml")
    simulation = create_simulation(config_path)
    print([room.doors for room in simulation.space[0].floors[0].rooms])
    print("Simulation created successfully...")

    plot_path = Path("../simulation_outputs") if plot else None
    record_filename = Path("../simulation_outputs/agent_states.csv") if record else None
    while simulation.time < simulation.total_simulation_time:
        simulation.step(
            plot_path=plot_path,
            record_filename=record_filename,
            record=record,
        )

    print("Simulation completed successfully...")


if __name__ == "__main__":
    time_start = time.time()
    simulate(plot=False, record=True)
    time_end = time.time()
    print(f"Simulation run time: {time_end - time_start} seconds")
