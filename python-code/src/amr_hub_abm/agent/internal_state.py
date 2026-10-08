"""Typed internal state and configuration for simulation agents."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from amr_hub_abm.agent.enums import AgentType
from amr_hub_abm.exceptions import InvalidDefinitionError, NonNegativeValueError


def _validate_level(name: str, value: float) -> None:
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        msg = f"{name} must be between 0.0 and 1.0."
        raise InvalidDefinitionError(msg)


def _validate_rate(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        msg = f"{name} must be finite and non-negative."
        raise NonNegativeValueError(msg)


@dataclass
class InternalState:
    """
    Current normalized internal needs of an agent.

    ``fatigue`` is ``None`` for patients because fatigue is not modelled for
    them in this first state-only implementation.
    """

    hunger: float = 0.0
    toilet_need: float = 0.0
    fatigue: float | None = None

    def __post_init__(self) -> None:
        """Validate state levels."""
        _validate_level("hunger", self.hunger)
        _validate_level("toilet_need", self.toilet_need)
        if self.fatigue is not None:
            _validate_level("fatigue", self.fatigue)

    @classmethod
    def for_agent_type(
        cls,
        agent_type: AgentType,
        *,
        hunger: float = 0.0,
        toilet_need: float = 0.0,
        fatigue: float = 0.0,
    ) -> InternalState:
        """Construct role-appropriate state."""
        return cls(
            hunger=hunger,
            toilet_need=toilet_need,
            fatigue=fatigue if agent_type == AgentType.HEALTHCARE_WORKER else None,
        )

    def update(
        self,
        *,
        hunger_rate: float,
        toilet_rate: float,
        fatigue_rate: float = 0.0,
    ) -> None:
        """Increase needs by one timestep, capped at one."""
        _validate_rate("hunger_rate", hunger_rate)
        _validate_rate("toilet_rate", toilet_rate)
        _validate_rate("fatigue_rate", fatigue_rate)
        self.hunger = min(1.0, self.hunger + hunger_rate)
        self.toilet_need = min(1.0, self.toilet_need + toilet_rate)
        if self.fatigue is not None:
            self.fatigue = min(1.0, self.fatigue + fatigue_rate)

    def reset(
        self,
        *,
        hunger: bool = False,
        toilet_need: bool = False,
        fatigue: bool = False,
    ) -> None:
        """Reset selected needs to zero for future task integrations."""
        if hunger:
            self.hunger = 0.0
        if toilet_need:
            self.toilet_need = 0.0
        if fatigue and self.fatigue is not None:
            self.fatigue = 0.0


@dataclass(frozen=True)
class InternalStateConfig:
    """Configured initial values and per-timestep rates for internal needs."""

    hcw_initial_fatigue: float
    hcw_initial_hunger: float
    hcw_initial_toilet_need: float
    patient_initial_hunger: float
    patient_initial_toilet_need: float
    hcw_fatigue_rate: float
    hcw_hunger_rate: float
    hcw_toilet_rate: float
    patient_hunger_rate: float
    patient_toilet_rate: float

    @classmethod
    def from_config(cls, config_data: dict[str, Any]) -> InternalStateConfig:
        """Build state configuration from YAML data."""
        keys = (
            "hcw_initial_fatigue",
            "hcw_initial_hunger",
            "hcw_initial_toilet_need",
            "patient_initial_hunger",
            "patient_initial_toilet_need",
            "hcw_fatigue_rate",
            "hcw_hunger_rate",
            "hcw_toilet_rate",
            "patient_hunger_rate",
            "patient_toilet_rate",
        )
        missing = [key for key in keys if key not in config_data]
        if missing:
            msg = (
                f"Missing required internal state config key(s): {', '.join(missing)}."
            )
            raise InvalidDefinitionError(msg)
        result = cls(**{key: config_data[key] for key in keys})
        for name in (
            "hcw_initial_fatigue",
            "hcw_initial_hunger",
            "hcw_initial_toilet_need",
            "patient_initial_hunger",
            "patient_initial_toilet_need",
        ):
            _validate_level(name, getattr(result, name))
        for name in (
            "hcw_fatigue_rate",
            "hcw_hunger_rate",
            "hcw_toilet_rate",
            "patient_hunger_rate",
            "patient_toilet_rate",
        ):
            _validate_rate(name, getattr(result, name))
        return result

    def initial_state(self, agent_type: AgentType) -> InternalState:
        """Create initial state for an agent role."""
        if agent_type == AgentType.HEALTHCARE_WORKER:
            return InternalState.for_agent_type(
                agent_type,
                fatigue=self.hcw_initial_fatigue,
                hunger=self.hcw_initial_hunger,
                toilet_need=self.hcw_initial_toilet_need,
            )
        return InternalState.for_agent_type(
            agent_type,
            hunger=self.patient_initial_hunger,
            toilet_need=self.patient_initial_toilet_need,
        )

    def update_state(self, state: InternalState, agent_type: AgentType) -> None:
        """Advance one agent's state by one timestep."""
        if agent_type == AgentType.HEALTHCARE_WORKER:
            state.update(
                hunger_rate=self.hcw_hunger_rate,
                toilet_rate=self.hcw_toilet_rate,
                fatigue_rate=self.hcw_fatigue_rate,
            )
        else:
            state.update(
                hunger_rate=self.patient_hunger_rate,
                toilet_rate=self.patient_toilet_rate,
            )
