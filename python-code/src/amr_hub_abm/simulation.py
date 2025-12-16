"""The main simulation module for the AMR Hub ABM."""

from dataclasses import dataclass
from enum import Enum

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
