"""Tests for healthcare-worker needs policy configuration."""

import pytest

from amr_hub_abm.agent.internal_state import InternalState
from amr_hub_abm.agent.needs_policy import Need, NeedRule, NeedsPolicy
from amr_hub_abm.exceptions import InvalidDefinitionError


def test_needs_policy_disabled_by_default() -> None:
    """Existing configurations do not activate autonomy."""
    assert NeedsPolicy.from_config({}) is None
    assert NeedsPolicy.from_config({"needs_policy": {"enabled": False}}) is None


def test_needs_policy_orders_urgent_needs_before_priority() -> None:
    """Urgency takes precedence, then integer priority and stable ties."""
    policy = NeedsPolicy(
        fatigue=NeedRule(0.5, 0.9, 2, 100),
        hunger=NeedRule(0.5, 0.8, 2, 1),
        toilet_need=NeedRule(0.5, 0.8, 2, 2),
        eating_building="Hospital",
        eating_floor=0,
        eating_room="Restaurant",
    )
    state = InternalState(fatigue=0.5, hunger=0.8, toilet_need=0.8)
    assert policy.eligible(state) == [Need.TOILET, Need.HUNGER, Need.FATIGUE]


@pytest.mark.parametrize(
    ("threshold", "urgent", "duration", "priority"),
    [
        (0.8, 0.7, 1, 1),
        (0.0, 0.9, 1, 1),
        (0.5, 1.1, 1, 1),
        (0.5, 0.9, 0, 1),
        (0.5, 0.9, 1, True),
    ],
)
def test_need_rule_rejects_invalid_values(
    threshold: float, urgent: float, duration: int, priority: int
) -> None:
    """Reject invalid thresholds, durations and priorities."""
    with pytest.raises(InvalidDefinitionError):
        NeedRule(threshold, urgent, duration, priority)


def test_enabled_policy_requires_all_rules() -> None:
    """Do not silently enable a partial policy."""
    with pytest.raises(InvalidDefinitionError, match="fatigue"):
        NeedsPolicy.from_config(
            {
                "needs_policy": {
                    "enabled": True,
                    "eating_room": {"building": "Hospital", "floor": 0, "name": "R"},
                }
            }
        )


def test_enabled_policy_parses_qualified_eating_room() -> None:
    """Parse all explicit rules and the eating room."""
    rule = {"threshold": 0.4, "urgent_threshold": 0.8, "duration": 3, "priority": 7}
    policy = NeedsPolicy.from_config(
        {
            "needs_policy": {
                "enabled": True,
                "eating_room": {"building": "Hospital", "floor": 0, "name": "R"},
                "fatigue": rule,
                "hunger": rule,
                "toilet_need": rule,
            }
        }
    )
    assert policy is not None
    assert policy.eating_room == "R"
    assert policy.hunger == NeedRule(0.4, 0.8, 3, 7)
