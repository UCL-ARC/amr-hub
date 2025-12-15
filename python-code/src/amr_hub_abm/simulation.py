"""The main simulation module for the AMR Hub ABM."""

from dataclasses import dataclass, field
from enum import Enum

from amr_hub_abm.agent import Agent
from amr_hub_abm.exceptions import TimeError
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
