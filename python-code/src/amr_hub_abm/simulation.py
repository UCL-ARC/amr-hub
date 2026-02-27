"""The main simulation module for the AMR Hub ABM."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from matplotlib import pyplot as plt

from amr_hub_abm.exceptions import TimeError

if TYPE_CHECKING:
    from pathlib import Path

    from matplotlib.axes import Axes

    from amr_hub_abm.agent import Agent
    from amr_hub_abm.space.building import Building
    from amr_hub_abm.space.room import Room


class SimulationMode(Enum):
    """Enumeration of simulation modes."""

    SPATIAL = "spatial"
    TOPOLOGICAL = "topological"


# --8<--- [start:Simulation]
@dataclass
class Simulation:
    """Representation of the AMR Hub ABM simulation."""

    name: str
    description: str
    mode: SimulationMode

    space: list[Building]
    agents: list[Agent]

    total_simulation_time: int

    time: int = field(default=0, init=False)

    # --8<--- [end:Simulation]

    def step(self, plot_path: Path | None = None) -> None:
        """Advance the simulation by one time step."""
        if self.time >= self.total_simulation_time:
            msg = "Simulation has already reached its total simulation time."
            raise TimeError(msg)

        # randomize agent order each step to avoid bias
        random.shuffle(self.agents)

        for agent in self.agents:
            agent.perform_task(current_time=self.time, rooms=self.rooms)

        if plot_path is not None:
            self.plot_current_state(directory_path=plot_path)

        self.time += 1

    def plot_current_state(self, directory_path: Path) -> None:
        """Plot the current state of the simulation."""
        if directory_path.suffix != "":
            msg = f"The path {directory_path} is not a directory."
            raise NotADirectoryError(msg)
        directory_path.mkdir(parents=True, exist_ok=True)

        for building in self.space:
            axes: list[Axes] = [plt.subplots(nrows=len(building.floors), ncols=1)[1]]
            building.plot_building(axes=axes, agents=self.agents)
            simulation_name = f"Simulation: {self.name}"
            time = f"Time: {self.time}/{self.total_simulation_time}"
            plt.suptitle(f"{simulation_name} | {time}")
            plt.savefig(
                directory_path
                / f"plot_{self.name}_building_{building.name}_time_{self.time}.png"
            )
            plt.close()

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
