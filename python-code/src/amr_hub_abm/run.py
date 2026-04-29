"""Module to run the AMR Hub ABM simulation."""

import logging
from pathlib import Path

from matplotlib import pyplot as plt

from amr_hub_abm.agent import InfectionStatus
from amr_hub_abm.simulation import Simulation
from amr_hub_abm.simulation_factory import create_simulation

logger = logging.getLogger(__name__)


def simulate(
    *,
    plot: bool = False,
    record: bool = False,
    live: bool = False,
    plot_trajectory: bool = False,
    seed_infections: bool = False,
) -> None:
    """Simulate the AMR Hub ABM based on a configuration file."""
    config_path = Path("tests/inputs/simulation_config.yml")
    simulation = create_simulation(config_path)
    if seed_infections:
        simulation.agents[0].infection_status = InfectionStatus.INFECTED
        simulation.agents[1].infection_status = InfectionStatus.EXPOSED

    if plot:
        output_dir = Path("../simulation_outputs")
        output_dir.mkdir(parents=True, exist_ok=True)

    logger.info([room.doors for room in simulation.space[0].floors[0].rooms])
    for agent in simulation.agents:
        msg = f"Agent {agent.agent_type, agent.idx} task list"
        logger.info(msg)
        msg = f"{[task.task_type.value for task in agent.tasks]}"
        logger.info(msg)
    logger.info("Simulation created successfully...")

    plot_path = Path("../simulation_outputs") if plot else None

    figures = simulation.setup_live_plot() if live else None

    run_steps(
        simulation,
        plot_path,
        record=record,
        figures=figures,
        trajectory=plot_trajectory,  # <- reuse your existing flag
    )

    if plot_trajectory:
        record = True
        plot_path = Path("../simulation_outputs")

    if record:
        logger.info("Recording agent states to CSV...")
        record_path = Path("../simulation_outputs/agent_states.csv")
        simulation.record_agent_states(record_path)

        if plot_trajectory:
            logger.info("Plotting agent trajectories...")
            if plot_path is None:
                msg = "Plot path must be provided to plot agent trajectories."
                raise ValueError(msg)
            simulation.plot_agent_trajectories(record_path)

    logger.info("Simulation completed successfully...")

    if live:
        plt.ioff()  # turn interactive mode off
        plt.show()  # final blocking show so window stays up after sim ends


def run_steps(
    simulation: Simulation,
    plot_path: Path | None,
    *,
    record: bool,
    figures: list | None = None,
    trajectory: bool = False,  # NEW
) -> None:
    """Run the simulation loop until completion, optionally plotting live."""
    while simulation.time < simulation.total_simulation_time:
        simulation.step(plot_path=plot_path, record=record)

        if figures is not None and simulation.time % 100 == 0:
            simulation.plot_live(figures, trajectory=trajectory)
