"""Module to run the AMR Hub ABM simulation."""

import csv
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from amr_hub_abm.simulation import Simulation
from amr_hub_abm.simulation_factory import create_simulation

logger = logging.getLogger(__name__)


@contextmanager
def state_recorder(filename: Path) -> Iterator:
    """Context manager to handle recording agent states to a CSV file."""
    # Setup (equivalent to __enter__)
    with filename.open("w", newline="", buffering=1024 * 1024) as f:
        writer = csv.writer(f)

        writer.writerow(
            [
                "time",
                "agent_id",
                "x",
                "y",
                "heading",
                "interaction_radius",
                "agent_type",
                "infection_status",
            ]
        )

        yield writer


def simulate(*, plot: bool = False, record: bool = False) -> None:
    """Simulate the AMR Hub ABM based on a configuration file."""
    config_path = Path("tests/inputs/simulation_config.yml")
    simulation = create_simulation(config_path)

    logger.info([room.doors for room in simulation.space[0].floors[0].rooms])
    logger.info("Simulation created successfully...")

    plot_path = Path("../simulation_outputs") if plot else None
    record_filename = Path("../simulation_outputs/agent_states.csv") if record else None

    if not record_filename:
        run_steps(simulation, plot_path, record_filename, record=record)
        logger.info("Simulation completed successfully...")
        return

    with state_recorder(record_filename) as writer:
        run_steps(simulation, plot_path, record_filename, record=record, writer=writer)

    logger.info("Simulation completed successfully...")


def run_steps(
    simulation: Simulation,
    plot_path: Path | None,
    record_filename: Path | None,
    *,
    record: bool,
    writer=None,
) -> None:
    """Run the simulation steps until completion."""
    while simulation.time < simulation.total_simulation_time:
        simulation.step(
            plot_path=plot_path,
            record_filename=record_filename,
            record=record,
            writer=writer,
        )
