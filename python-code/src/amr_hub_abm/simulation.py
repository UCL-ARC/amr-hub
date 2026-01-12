"""The main simulation module for the AMR Hub ABM."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from matplotlib import pyplot as plt

from amr_hub_abm.exceptions import TimeError

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from amr_hub_abm.agent import Agent
    from amr_hub_abm.space.building import Building


class SimulationMode(Enum):
    """Enumeration of simulation modes."""

    SPATIAL = "spatial"
    TOPOLOGICAL = "topological"


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

    def step(self) -> None:
        """Advance the simulation by one time step."""
        if self.time >= self.total_simulation_time:
            msg = "Simulation has already reached its total simulation time."
            raise TimeError(msg)

        self.time += 1

    def plot_current_state(self) -> None:
        """Plot the current state of the simulation."""
        for building in self.space:
            axes: list[Axes] = [plt.subplots(nrows=len(building.floors), ncols=1)[1]]
            building.plot_building(axes=axes, agents=self.agents)
            simulation_name = f"Simulation: {self.name}"
            time = f"Time: {self.time}/{self.total_simulation_time}"
            plt.suptitle(f"{simulation_name} | {time}")
            plt.savefig(
                f"simulation_{self.name}_building_{building.name}_time_{self.time}.png"
            )
            plt.close()
