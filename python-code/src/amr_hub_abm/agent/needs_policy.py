"""Configuration and decisions for healthcare-worker needs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import TYPE_CHECKING

from amr_hub_abm.exceptions import InvalidDefinitionError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from amr_hub_abm.agent.internal_state import InternalState


class Need(StrEnum):
    """Needs that can cause a healthcare worker to take a break."""

    FATIGUE = "fatigue"
    HUNGER = "hunger"
    TOILET = "toilet_need"


@dataclass(frozen=True)
class NeedRule:
    """Thresholds, duration and priority for one need."""

    threshold: float
    urgent_threshold: float
    duration: int
    priority: int

    def __post_init__(self) -> None:
        """Validate model parameters."""
        for name, value in (
            ("threshold", self.threshold),
            ("urgent_threshold", self.urgent_threshold),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0 <= value <= 1
            ):
                msg = f"{name} must be a finite number between 0 and 1."
                raise InvalidDefinitionError(msg)
        if self.urgent_threshold < self.threshold:
            msg = "urgent_threshold must not be less than threshold."
            raise InvalidDefinitionError(msg)
        if self.threshold == 0:
            msg = "threshold must be greater than zero."
            raise InvalidDefinitionError(msg)
        if isinstance(self.duration, bool) or not isinstance(self.duration, int):
            msg = "Need duration must be a positive integer."
            raise InvalidDefinitionError(msg)
        if self.duration <= 0:
            msg = "Need duration must be a positive integer."
            raise InvalidDefinitionError(msg)
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            msg = "Need priority must be an integer."
            raise InvalidDefinitionError(msg)

    @classmethod
    def from_config(cls, value: object, need: Need) -> NeedRule:
        """Parse one explicitly configured rule."""
        if not isinstance(value, dict):
            msg = f"needs_policy.{need.value} must be a mapping."
            raise InvalidDefinitionError(msg)
        keys = ("threshold", "urgent_threshold", "duration", "priority")
        if any(key not in value for key in keys):
            msg = f"needs_policy.{need.value} requires {', '.join(keys)}."
            raise InvalidDefinitionError(msg)
        threshold = value["threshold"]
        urgent_threshold = value["urgent_threshold"]
        duration = value["duration"]
        priority = value["priority"]
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or isinstance(urgent_threshold, bool)
            or not isinstance(urgent_threshold, (int, float))
            or isinstance(duration, bool)
            or not isinstance(duration, int)
            or isinstance(priority, bool)
            or not isinstance(priority, int)
        ):
            msg = f"Invalid parameter types for needs_policy.{need.value}."
            raise InvalidDefinitionError(msg)
        return cls(threshold, urgent_threshold, duration, priority)


@dataclass(frozen=True)
class NeedsPolicy:
    """Opt-in need rules and the qualified room used for meals."""

    fatigue: NeedRule
    hunger: NeedRule
    toilet_need: NeedRule
    eating_building: str
    eating_floor: int
    eating_room: str

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> NeedsPolicy | None:
        """Parse an optional needs policy."""
        block = config.get("needs_policy")
        if block is None:
            return None
        if not isinstance(block, dict):
            msg = "needs_policy must be a mapping."
            raise InvalidDefinitionError(msg)
        enabled = block.get("enabled", False)
        if not isinstance(enabled, bool):
            msg = "needs_policy.enabled must be a boolean."
            raise InvalidDefinitionError(msg)
        if not enabled:
            return None
        room = block.get("eating_room")
        if not isinstance(room, dict):
            msg = "needs_policy.eating_room must identify building, floor and room."
            raise InvalidDefinitionError(msg)
        building = room.get("building")
        floor = room.get("floor")
        name = room.get("name")
        if (
            not isinstance(building, str)
            or not building
            or isinstance(floor, bool)
            or not isinstance(floor, int)
            or not isinstance(name, str)
            or not name
        ):
            msg = (
                "needs_policy.eating_room requires a building, integer floor and name."
            )
            raise InvalidDefinitionError(msg)
        return cls(
            fatigue=NeedRule.from_config(block.get("fatigue"), Need.FATIGUE),
            hunger=NeedRule.from_config(block.get("hunger"), Need.HUNGER),
            toilet_need=NeedRule.from_config(block.get("toilet_need"), Need.TOILET),
            eating_building=building,
            eating_floor=floor,
            eating_room=name,
        )

    def rule(self, need: Need) -> NeedRule:
        """Return the rule associated with a need."""
        return getattr(self, need.value)

    def eligible(self, state: InternalState) -> list[Need]:
        """Order eligible needs by urgency, priority and stable need order."""
        eligible = [
            need
            for need in Need
            if (level := getattr(state, need.value)) is not None
            and level >= self.rule(need).threshold
        ]
        return sorted(
            eligible,
            key=lambda need: (
                -int(getattr(state, need.value) >= self.rule(need).urgent_threshold),
                -self.rule(need).priority,
                need.value,
            ),
        )
