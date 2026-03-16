from pathlib import Path
import time
import logging

logger = logging.getLogger(__name__)

from amr_hub_abm.simulation_factory import create_simulation


def simulate(plot: bool = False) -> None:
    config_path = Path("tests/inputs/simulation_config.yml")
    simulation = create_simulation(config_path)
    logger.info([room.doors for room in simulation.space[0].floors[0].rooms])
    logger.info("Simulation created successfully...")

    while simulation.time < simulation.total_simulation_time:
        simulation.step(plot_path=Path("../simulation_outputs") if plot else None)


if __name__ == "__main__":
    time_start = time.perf_counter()
    simulate(plot=False)
    time_end = time.perf_counter()
    logger.info("Simulation run time: %s seconds", time_end - time_start)
