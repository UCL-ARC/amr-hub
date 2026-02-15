"""Module to run the AMR Hub ABM simulation."""

import logging
from pathlib import Path

from amr_hub_abm.simulation_factory import create_simulation

logger = logging.getLogger(__name__)


def simulate(*, plot: bool = False, record: bool = False) -> None:
    """Simulate the AMR Hub ABM based on a configuration file."""
    config_path = Path("tests/inputs/simulation_config.yml")
    simulation = create_simulation(config_path)

    logger.info([room.doors for room in simulation.space[0].floors[0].rooms])
    logger.info("Simulation created successfully...")

    plot_path = Path("../simulation_outputs") if plot else None
    record_filename = Path("../simulation_outputs/agent_states.csv") if record else None
    while simulation.time < simulation.total_simulation_time:
        simulation.step(
            plot_path=plot_path,
            record_filename=record_filename,
            record=record,
        )

    logger.info("Simulation completed successfully...")
