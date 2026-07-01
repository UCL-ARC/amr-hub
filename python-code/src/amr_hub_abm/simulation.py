"""The main simulation module for the AMR Hub ABM."""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import TYPE_CHECKING, Any

import mesa
import numpy as np
from matplotlib import pyplot as plt

from amr_hub_abm.exceptions import TimeError
from amr_hub_abm.gpu_physics import GPUPhysicsEngine
from amr_hub_abm.space.space import SpatialQuery

if TYPE_CHECKING:
    from pathlib import Path

    from matplotlib.axes import Axes

    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.space.building import Building
    from amr_hub_abm.space.room import Room

logger = logging.getLogger(__name__)


class SimulationMode(IntEnum):
    """Enumeration of simulation modes."""

    SPATIAL = 0
    TOPOLOGICAL = 1


# --8<--- [start:Simulation]
class Simulation(mesa.Model):
    """
    Representation of the AMR Hub ABM simulation.

    This class encapsulates the entire state and behavior of the simulation,
    including the space (buildings, floors, rooms), the agents, and the logic
    for advancing the simulation through time steps.

    Parameters
    ----------
    name : str
        The name of the simulation.
    description : str
        A brief description of the simulation.
    mode : SimulationMode
        The mode of the simulation (SPATIAL or TOPOLOGICAL).
    space : list[Building]
        The simulation space represented as a list of Building instances.
    agents : list[Agent]
        The list of Agent instances in the simulation.
    total_simulation_time : int
        The total number of time steps in the simulation.
    rng_generator : np.random.Generator
        Random number generator for reproducibility.
    use_gpu : bool, optional
        Whether to use GPU acceleration, by default False.

    """

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        description: str,
        mode: SimulationMode,
        space: list[Building],
        agents: list[Agent],
        total_simulation_time: int,
        rng_generator: np.random.Generator,
        *,
        use_gpu: bool = False,
    ) -> None:
        """Initialise the simulation model with space, agents, and engine."""
        super().__init__()

        self.name = name
        self.description = description
        self.mode = mode
        self.space = space
        self.total_simulation_time = total_simulation_time
        self.rng_generator = rng_generator
        self.use_gpu = use_gpu

        # Mesa scheduler — RandomActivation shuffles agent order each step,
        # replacing the manual rng_generator.shuffle(self.agents) call.
        self.schedule = mesa.time.RandomActivation(self)

        # Spatial engine — one instance shared by all agents via the scheduler.
        self.gpu_engine: Any = None
        self.spatial_engine: SpatialQuery | None = None

        if use_gpu:
            self.gpu_engine = GPUPhysicsEngine()
        else:
            self.spatial_engine = SpatialQuery(space=self.space)

        # Register agents with the Mesa scheduler.
        # NOTE: Mesa agents need a unique_id and a model reference.
        self._agents = agents
        for agent in agents:
            self.schedule.add(agent)

    # --8<--- [end:Simulation]

    @property
    def time(self) -> int:
        """Current simulation time, driven by the Mesa scheduler."""
        return self.schedule.steps

    @property
    def agents_list(self) -> list[Agent]:
        """Access the original agent list (for plotting, recording, etc.)."""
        return self._agents

    # --------------------------------------------------------------------------
    def step(self, plot_path: Path | None = None) -> None:
        """
        Advance the simulation by one time step.

        Mesa's ``RandomActivation`` scheduler shuffles agents and calls
        ``agent.step()`` on each one, which in turn calls
        ``agent.perform_task(current_time, engine)``.

        Parameters
        ----------
        plot_path : Path | None
            Directory to save the plot of the current state. If None, no
            plot is saved.

        """
        if self.time >= self.total_simulation_time:
            msg = "Simulation has already reached its total simulation time."
            raise TimeError(msg)

        if self.use_gpu:
            self.gpu_engine.step_physics(self._agents)

        if plot_path is not None and not self.use_gpu:
            self.plot_current_state(directory_path=plot_path)

    # --------------------------------------------------------------------------
    def plot_current_state(
        self, directory_path: Path, *, trajectory: bool = False
    ) -> None:
        """
        Plot the current state of the simulation.

        Parameters
        ----------
        directory_path : Path
            The directory where the plots will be saved.
        trajectory : bool, optional
            Whether to plot agent trajectories, by default False.

        """
        if directory_path.suffix != "":
            msg = f"The path {directory_path} is not a directory."
            raise NotADirectoryError(msg)
        directory_path.mkdir(parents=True, exist_ok=True)

        for building in self.space:
            axes: list[Axes] = [plt.subplots(nrows=len(building.floors), ncols=1)[1]]
            building.plot_building(
                axes=axes, agents=self._agents, trajectory=trajectory
            )
            simulation_name = f"Simulation: {self.name}"
            if trajectory:
                simulation_name += " | Agent Trajectories"
                filename = f"{building.name}_trajectories.png"
            else:
                simulation_name += f" | Time: {self.time}/{self.total_simulation_time}"
                filename = f"{building.name}_time_{self.time}.png"
            plt.suptitle(simulation_name)
            plt.savefig(directory_path / filename)
            plt.close()

    def plot_live(
        self,
        figures: list,
        *,
        pause: float = 0.05,
        trajectory: bool = False,
    ) -> None:
        """
        Update existing figures in place with current agent positions.

        Parameters
        ----------
        figures : list
            A list of tuples containing (building, figure, axes).
        pause : float, optional
            Time to pause after updating plots, by default 0.05 seconds.
        trajectory : bool, optional
            Whether to include agent trajectories, by default False.

        """
        for building, fig, axes in figures:
            for ax in axes:
                ax.clear()

            building.plot_building(
                axes=axes,
                agents=self._agents,
                trajectory=trajectory,
            )

            title = (
                f"Simulation: {self.name} | "
                f"Time: {self.time}/{self.total_simulation_time}"
            )
            if trajectory:
                title += " | Trajectories"

            fig.suptitle(title)
            fig.canvas.draw_idle()
            fig.canvas.flush_events()

        plt.pause(pause)

    def setup_live_plot(self) -> list:
        """
        Create reusable figures for live plotting.

        Returns
        -------
        list
            A list of tuples (building, figure, axes) for each building.

        """
        plt.ion()
        figures = []
        for building in self.space:
            fig, axes = plt.subplots(
                nrows=len(building.floors),
                ncols=1,
                figsize=(10, 6 * len(building.floors)),
            )
            axes = [axes] if len(building.floors) == 1 else list(axes)
            figures.append((building, fig, axes))
        plt.show(block=False)
        return figures

    def __repr__(self) -> str:
        """Representation of the simulation."""
        header = f"Simulation: {self.name}\nDescription: {self.description}\n"
        header += f"Mode: {self.mode.value}\n"
        header += f"Total Simulation Time: {self.total_simulation_time}\n"
        header += f"Current Time: {self.time}\n"
        header += f"Number of Buildings: {len(self.space)}\n"
        header += f"Number of Agents: {len(self._agents)}\n"

        buildings_repr = "\n".join([repr(building) for building in self.space])
        agents_repr = "\n".join([repr(agent) for agent in self._agents])

        return f"{header}\nBuildings:\n{buildings_repr}\n\nAgents:\n{agents_repr}"

    @property
    def rooms(self) -> list[Room]:
        """Get all rooms in the simulation space."""
        all_rooms: list[Room] = []
        for building in self.space:
            for floor in building.floors:
                all_rooms.extend(floor.rooms)
        return all_rooms

    @property
    def agents(self) -> list[Agent]:
        """Agent list, preserving the existing API."""
        return self._agents

    def record_agent_states(self, file_path: Path) -> None:
        """
        Record the states of all agents to CSV files.

        Parameters
        ----------
        file_path : Path
            The path to the CSV file where agent states will be recorded.

        """
        for agent in self._agents:
            agent_filename = (
                file_path.parent
                / f"agent_{agent.agent_type.value}_{agent.idx}_trajectory.csv"
            )

            np.savetxt(
                agent_filename,
                np.column_stack(
                    [
                        np.arange(len(agent.trajectory.position)),
                        agent.trajectory.building,
                        agent.trajectory.floor,
                        agent.trajectory.position,
                        agent.trajectory.heading.T.flatten(),
                        agent.trajectory.infection_status,
                    ]
                ),
                delimiter=",",
                header="time,building,floor,x,y,heading,infection_status",
                comments="",
            )

    def plot_agent_trajectories(self, output_file: Path) -> None:
        """
        Plot the trajectories of all agents from a recorded CSV file.

        Parameters
        ----------
        output_file : Path
            The path to the CSV file containing the agent trajectories.

        """
        self.plot_current_state(directory_path=output_file.parent, trajectory=True)
