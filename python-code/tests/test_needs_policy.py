"""Tests for healthcare-worker needs policy configuration."""

from dataclasses import replace

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
        travel_timeout=20,
        retry_interval=5,
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
                    "travel_timeout": 20,
                    "retry_interval": 5,
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
                "travel_timeout": 20,
                "retry_interval": 5,
                "fatigue": rule,
                "hunger": rule,
                "toilet_need": rule,
            }
        }
    )
    assert policy is not None
    assert policy.eating_room == "R"
    assert policy.hunger == NeedRule(0.4, 0.8, 3, 7)


@pytest.mark.parametrize("duration", [True, 1.5, "2"])
def test_need_rule_rejects_non_integer_duration(duration: object) -> None:
    """Durations cannot be booleans, fractions, or strings."""
    with pytest.raises(InvalidDefinitionError, match="duration"):
        NeedRule(0.5, 0.9, duration, 1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"threshold": 0.5}, "requires"),
        (
            {"threshold": True, "urgent_threshold": 0.9, "duration": 2, "priority": 1},
            "Invalid parameter types",
        ),
    ],
)
def test_need_rule_config_rejects_missing_or_invalid_fields(
    value: dict[str, object], message: str
) -> None:
    """A malformed rule cannot activate an incomplete needs policy."""
    with pytest.raises(InvalidDefinitionError, match=message):
        NeedRule.from_config(value, Need.FATIGUE)


@pytest.mark.parametrize(
    ("block", "message"),
    [
        ("enabled", "must be a mapping"),
        ({"enabled": "yes"}, "enabled must be a boolean"),
        ({"enabled": True}, "eating_room must identify"),
        (
            {"enabled": True, "eating_room": {"building": "A", "floor": True}},
            "requires",
        ),
        (
            {
                "enabled": True,
                "eating_room": {"building": "A", "floor": 0, "name": "R"},
                "travel_timeout": 0,
                "retry_interval": 2,
            },
            "travel_timeout and retry_interval",
        ),
    ],
)
def test_needs_policy_rejects_invalid_configuration(
    block: object, message: str
) -> None:
    """Malformed enabled policy configuration fails before scheduling."""
    with pytest.raises(InvalidDefinitionError, match=message):
        NeedsPolicy.from_config({"needs_policy": block})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"eating_building": ""}, "eating room"),
        ({"eating_floor": True}, "eating room"),
        ({"travel_timeout": 0}, "Travel timeout"),
        ({"retry_interval": True}, "Travel timeout"),
    ],
)
def test_direct_policy_construction_validates_facility_and_timing(
    changes: dict[str, object], message: str
) -> None:
    """Direct construction enforces the same invariants as config parsing."""
    rule = NeedRule(0.5, 0.9, 2, 1)
    policy = NeedsPolicy(rule, rule, rule, "Hospital", 0, "Restaurant", 20, 5)
    with pytest.raises(InvalidDefinitionError, match=message):
        replace(policy, **changes)
