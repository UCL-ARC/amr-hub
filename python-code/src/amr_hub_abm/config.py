"""Module to store configuration parameters for the AMR Hub ABM simulation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from amr_hub_abm.agent.kinematics import AgentKinematicsConfig
from amr_hub_abm.task.task_duration import TaskDurationConfig


@dataclass(frozen=True)
class SimulationConfig:
    """
    Configuration parameters for the AMR Hub ABM simulation.

    Parameters
    ----------
    agent_kinematics : AgentKinematicsConfig
        Configuration parameters for agent kinematics.
    task_durations : TaskDurationConfig
        Configuration parameters for task durations.

    """

    agent_kinematics: AgentKinematicsConfig
    task_durations: TaskDurationConfig
    config_data: dict

    @classmethod
    def from_file(cls, config_path: Path) -> SimulationConfig:
        """
        Load simulation configuration from a YAML file.

        Parameters
        ----------
        config_path : Path
            Path to the YAML configuration file.

        Returns
        -------
        SimulationConfig
            The simulation configuration parameters.

        """
        with Path.open(config_path, "r", encoding="utf-8") as file:
            config_data = yaml.safe_load(file)

        agent_kinematics = AgentKinematicsConfig.from_config(config_data)
        task_durations = TaskDurationConfig.from_config(config_data)

        return cls(
            agent_kinematics=agent_kinematics,
            task_durations=task_durations,
            config_data=config_data,
        )


sim_config = SimulationConfig.from_file(Path("tests/inputs/simulation_config.yml"))
