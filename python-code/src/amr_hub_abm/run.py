"""Module to run the AMR Hub ABM simulation."""

import logging
from pathlib import Path

from amr_hub_abm.simulation import Simulation
from amr_hub_abm.simulation_factory import create_simulation

logger = logging.getLogger(__name__)


def simulate(
    *,
    plot: bool = False,
    record: bool = False,
    plot_trajectory: bool = False,
    use_gpu: bool = False,
) -> None:
    """Simulate the AMR Hub ABM based on a configuration file."""
    config_path = Path("tests/inputs/simulation_config.yml")

    # 6/5/2026 NG Added to call the floor plan created by the new convertor
    if use_gpu:
        config_path = Path("tests/inputs/simulation_config_gpu.yml")

    simulation = create_simulation(config_path)
    # --------------------------------------------------------------------------
    # 6/5/2026 NG Added
    simulation.use_gpu = use_gpu
    for agent in simulation.agents:
        agent.use_gpu = use_gpu

    if use_gpu:
        logger.info("GPU Acceleration Enabled: Routing physics to NVIDIA Warp")
        if plot or plot_trajectory:
            logger.warning("PNG generation is disabled in GPU mode")
        plot = False
        plot_trajectory = False
    else:
        logger.info("CPU Mode Enabled: Using legacy Python movement logic")
    # --------------------------------------------------------------------------

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

    run_steps(simulation, plot_path, record=record)

    # --------------------------------------------------------------------------
    # NG: This should be reconsidered to create files rather than images
    if plot_trajectory:
        record = True
        plot_path = Path("../simulation_outputs")

    if record:
        logger.info("Recording agent states to CSV...")
        record_path = Path("simulation_outputs/agent_states.csv")

        # NG Fix Force the operating system to create the folder
        record_path.parent.mkdir(parents=True, exist_ok=True)
        simulation.record_agent_states(record_path)

        if plot_trajectory:
            logger.info("Plotting agent trajectories...")
            if plot_path is None:
                msg = "Plot path must be provided to plot agent trajectories."
                raise ValueError(msg)
            simulation.plot_agent_trajectories(record_path)
    # --------------------------------------------------------------------------

    # NG: Writes Results to Disk
    if getattr(simulation, "use_gpu", False) and simulation.gpu_engine is not None:
        logger.info("Exporting GPU Telemetry to disk")
        simulation.gpu_engine.export_data(output_dir="simulation_outputs")

    logger.info("Simulation completed successfully...")


def run_steps(
    simulation: Simulation,
    plot_path: Path | None,
    *,
    record: bool,
) -> None:
    """Run the simulation steps until completion."""
    while simulation.time < simulation.total_simulation_time:
        simulation.step(
            plot_path=plot_path,
            record=record,
        )


# Make True for GPU
if __name__ == "__main__":
    simulate(use_gpu=True, record=True)
