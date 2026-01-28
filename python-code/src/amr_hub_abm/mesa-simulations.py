"""The main simulation module for the AMR Hub ABM."""
from dataclasses import dataclass
from enum import Enum
from mesa import Model
from mesa.time import BaseScheduler
from mesa.space import ContinuousSpace

from amr_hub_abm.agent import Agent
from amr_hub_abm.exceptions import TimeError
from amr_hub_abm.space.building import Building


class SimulationMode(Enum):
    """Enumeration of simulation modes."""
    SPATIAL = "spatial"
    TOPOLOGICAL = "topological"

@dataclass
class Simulation(Model):
    """Mesa-based simulation for AMR Hub ABM."""
    
    def __init__(
        self,
        name: str,
        description: str,
        mode: SimulationMode,
        space: list[Building],
        agents: list[Agent],
        total_simulation_time: int,
        width: float = 100.0,
        height: float = 100.0,
    ):
        """Initialize the simulation."""
        super().__init__()
        
        # existing attributes
        self.name = name
        self.description = description
        self.mode = mode
        self.space_buildings = space  # Renamed to avoid conflict with Mesa's space
        self.total_simulation_time = total_simulation_time
        self.time = 0
        
        # Extract all rooms for easy access
        self.rooms = []
        for building in space:
            for floor in building.floors:
                self.rooms.extend(floor.rooms)
        
        # Mesa components
        self.schedule = BaseScheduler(self)
        self.space = ContinuousSpace(width, height, torus=False)
        
        # Add agents to Mesa
        for agent in agents:
            agent.model = self  # Link agent to model
            self.schedule.add(agent)
            self.space.place_agent(agent, (agent.location.x, agent.location.y))
    
    def step(self) -> None:
        """Advance the simulation by one time step."""
        if self.time >= self.total_simulation_time:
            msg = "Simulation has already reached its total simulation time."
            raise TimeError(msg)
        
        self.time += 1
        self.schedule.step()  # This calls agent.step() for all agents
    
    def run(self, n_steps: int | None = None) -> None:
        """Run the simulation for n steps (or until completion)."""
        steps = n_steps if n_steps else self.total_simulation_time
        for _ in range(steps):
            if self.time >= self.total_simulation_time:
                break
            self.step()