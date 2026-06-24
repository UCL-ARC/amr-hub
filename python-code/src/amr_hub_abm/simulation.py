"""The main simulation module for the AMR Hub ABM."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any

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


class SimulationMode(IntEnum):
    """Enumeration of simulation modes."""

    SPATIAL = 0
    TOPOLOGICAL = 1


# --8<--- [start:Simulation]
@dataclass
class Simulation:
    """
    Representation of the AMR Hub ABM simulation.

    This class encapsulates the entire state and behavior of the simulation, including
    the space (buildings, floors, rooms), the agents, and the logic for advancing
    the simulation through time steps. It also includes methods for plotting the current
    state of the simulation and recording agent states to files.

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

    """

    # ------------------------------------------------------------------------------
    name: str
    description: str
    mode: SimulationMode

    space: list[Building]
    agents: list[Agent]

    total_simulation_time: int
    rng_generator: np.random.Generator
    time: int = field(default=0, init=False)

    # NG Added Flag for GPU Acceleration
    use_gpu: bool = field(default=False)
    gpu_engine: Any = field(default=None, init=False)
    spatial_engine: Any = field(default=None, init=False)
    # ------------------------------------------------------------------------------

    def __post_init__(self) -> None:
        """Init for GPU to load CAD once at the start."""
        if self.use_gpu:
            self.gpu_engine = GPUPhysicsEngine()
        # Initialize the CPU engine
        else:
            self.spatial_engine = SpatialQuery(space=self.space)
            self._agent_store = None

    # ------------------------------------------------------------------------------
    def step(self, plot_path: Path | None = None, *, record: bool = False) -> None:
        """
        Advance the simulation by one time step.

        This method performs the following actions:

        1. Checks if the simulation has already reached its total simulation time
        and raises an error if so.

        2. Randomizes the order of agents to avoid bias in action execution.

        3. Iterates through each agent and calls their `perform_task` method to
        execute their current task.

        4. If a `plot_path` is provided, it calls the `plot_current_state` method to
        save a plot of the current state of the simulation.

        5. Increments the simulation time by one step.

        Parameters
        ----------
        plot_path : Path | None
            Directory to save the plot of the current state. If None, no plot is saved.
        record : bool
            Whether to record the state of agents during their task execution. Passed to
            the `perform_task` method of agents.

        """
        if self.time >= self.total_simulation_time:
            msg = "Simulation has already reached its total simulation time."
            raise TimeError(msg)

        # randomize agent order each step to avoid bias
        self.rng_generator.shuffle(self.agents)

        # NG: GPU Updates Agents
        if self.use_gpu:
            self.gpu_engine.step_physics(self.agents)  # Takes the step and query

        # CPU Updates all agents
        else:
            for agent in self.agents:
                agent.perform_task(
                    current_time=self.time, engine=self.spatial_engine, record=record
                )

            if plot_path is not None:
                self.plot_current_state(directory_path=plot_path)

        self.time += 1

    # ------------------------------------------------------------------------------

    def plot_current_state(
        self, directory_path: Path, *, trajectory: bool = False
    ) -> None:
        """
        Plot the current state of the simulation.

        This method iterates through each building in the simulation space and creates
        a plot of the building's layout along with the positions of agents. If the
        `trajectory` flag is set to True, it also plots the trajectories of agents up to
        the current time step. The plots are saved to the specified directory.

        Parameters
        ----------
        directory_path : Path
            The directory where the plots will be saved. The method will create the
            directory if it does not exist.
        trajectory : bool, optional
            Whether to plot agent trajectories up to the current time step,
            by default False.

        """
        if directory_path.suffix != "":
            msg = f"The path {directory_path} is not a directory."
            raise NotADirectoryError(msg)
        directory_path.mkdir(parents=True, exist_ok=True)

        for building in self.space:
            axes: list[Axes] = [plt.subplots(nrows=len(building.floors), ncols=1)[1]]
            building.plot_building(axes=axes, agents=self.agents, trajectory=trajectory)
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

        This method is designed for live plotting during the simulation run. It takes a
        list of figures and updates them with the current agent positions.
        If the `trajectory` flag is set to True, it also updates the plots with agent
        trajectories up to the current time step. The method uses `plt.pause` to create
        a brief pause after updating the plots to allow for visualization.

        Parameters
        ----------
        figures : list
            A list of tuples containing (building, figure, axes) for each building in
            the simulation.

        pause : float, optional
            The amount of time to pause after updating the plots, by default 0.05
            seconds.

        trajectory : bool, optional
            Whether to include agent trajectories in the live plot, by default False.

        """
        for building, fig, axes in figures:
            for ax in axes:
                ax.clear()

            building.plot_building(
                axes=axes,
                agents=self.agents,
                trajectory=trajectory,  # <- key change
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
        Create reusable figures for live plotting. Call once before the run loop.

        This method initializes Matplotlib figures for each building in the simulation
        space. It creates a subplot for each floor of the building and returns a list of
        tuples containing the building, figure, and axes. These figures can then be
        updated in place during the simulation run using the `plot_live` method.

        Returns
        -------
        list
            A list of tuples, where each tuple contains (building, figure, axes) for
            each building in the simulation.

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
        header += f"Number of Agents: {len(self.agents)}\n"

        buildings_repr = "\n".join([repr(building) for building in self.space])
        agents_repr = "\n".join([repr(agent) for agent in self.agents])

        return f"{header}\nBuildings:\n{buildings_repr}\n\nAgents:\n{agents_repr}"

    @property
    def rooms(self) -> list[Room]:
        """Get all rooms in the simulation space."""
        all_rooms: list[Room] = []
        for building in self.space:
            for floor in building.floors:
                all_rooms.extend(floor.rooms)
        return all_rooms

    def record_agent_states(self, file_path: Path) -> None:
        """
        Record the states of all agents at the current time step to a CSV file.

        This method saves the current state of each agent, including their position,
        heading, infection status, and other relevant attributes, to a CSV file at the
        specified path. The CSV file will have a header row and will be overwritten if
        it already exists.

        Parameters
        ----------
        file_path : Path
            The path to the CSV file where agent states will be recorded.

        """
        for agent in self.agents:
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
