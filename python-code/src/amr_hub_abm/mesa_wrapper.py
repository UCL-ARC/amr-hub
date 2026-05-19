"""Thin Mesa wrapper around the existing Simulation for SolaraViz."""

from pathlib import Path

import mesa

from amr_hub_abm.agent import InfectionStatus
from amr_hub_abm.simulation_factory import create_simulation


class HospitalABM(mesa.Model):
    """Mesa model wrapper around the AMR Hub simulation for visualization."""

    def __init__(
        self,
        agent_speed: float = 0.001,
        agent_stochasticity: float = 5.0,
        config_path: str = "tests/inputs/simulation_config.yml",
    ) -> None:
        """Initialize the model and seed infections for demo purposes."""
        super().__init__()

        self.agent_speed = agent_speed
        self.agent_stochasticity = agent_stochasticity

        self.simulation = create_simulation(
            Path(config_path),
            agent_speed=agent_speed,
            agent_stochasticity=agent_stochasticity,
        )

        # seed infections for visualization demo
        self.simulation.agents[0].infection_status = InfectionStatus.INFECTED
        self.simulation.agents[1].infection_status = InfectionStatus.EXPOSED

    def step(self) -> None:
        """Advance the wrapped simulation by one time step."""
        if self.simulation.time < self.simulation.total_simulation_time:
            self.simulation.step(record=True)
        else:
            self.running = False
