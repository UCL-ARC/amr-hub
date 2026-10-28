"""Module defining agent kinematics configuration for the AMR Hub ABM simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from amr_hub_abm.exceptions import InvalidDefinitionError


class MovementStrategy(StrEnum):
    """Available strategies for setting an agent's movement speed."""

    FIXED = "fixed"
    DEADLINE_PACED = "deadline_paced"


#: Keys that must be present in the simulation config file for agent kinematics.
REQUIRED_KINEMATICS_KEYS: tuple[str, ...] = (
    "agent_movement_speed",
    "agent_stochasticity",
    "agent_interaction_radius",
    "agent_max_movement_attempts",
)


@dataclass(frozen=True)
class AgentKinematicsConfig:
    """
    Agent kinematics parameters read from the simulation configuration file.

    Parameters
    ----------
    movement_speed : float
        Agent movement speed, in units per time step.
    stochasticity : float
        Degrees of randomness applied to an agent's heading at each step.
    movement_strategy : MovementStrategy
        Strategy used to set the agent's movement speed.
    interaction_radius: float
        Distance within which an agent is considered to have reached a target.
    max_movement_attempts : int
        Maximum number of attempts to find a movement step that avoids wall
        intersections.

    """

    movement_speed: float
    stochasticity: float
    interaction_radius: float
    max_movement_attempts: int
    movement_strategy: MovementStrategy = MovementStrategy.FIXED

    @classmethod
    def from_config(cls, config_data: dict[str, Any]) -> AgentKinematicsConfig:
        """
        Build an ``AgentKinematicsConfig`` from parsed YAML configuration data.

        The speed, stochasticity, interaction radius, and movement-attempt count
        must be defined explicitly. The movement strategy defaults to ``fixed``.

        Parameters
        ----------
        config_data : dict[str, Any]
            The parsed simulation configuration.

        Returns
        -------
        AgentKinematicsConfig
            The agent kinematics parameters read from the config.

        Raises
        ------
        InvalidDefinitionError
            If one or more required agent kinematics keys are missing from
            the config.

        """
        missing_keys = [
            key for key in REQUIRED_KINEMATICS_KEYS if key not in config_data
        ]
        if missing_keys:
            msg = (
                "Missing required agent kinematics config key(s): "
                f"{', '.join(missing_keys)}."
            )
            raise InvalidDefinitionError(msg)

        strategy_value = config_data.get(
            "agent_movement_strategy", MovementStrategy.FIXED.value
        )
        try:
            movement_strategy = MovementStrategy(strategy_value)
        except (TypeError, ValueError) as exc:
            msg = (
                "Invalid agent_movement_strategy "
                f"{strategy_value!r}; expected one of "
                f"{', '.join(strategy.value for strategy in MovementStrategy)}."
            )
            raise InvalidDefinitionError(msg) from exc

        return cls(
            movement_speed=config_data["agent_movement_speed"],
            stochasticity=config_data["agent_stochasticity"],
            interaction_radius=config_data["agent_interaction_radius"],
            max_movement_attempts=config_data["agent_max_movement_attempts"],
            movement_strategy=movement_strategy,
        )
