"""Tests for AgentKinematicsConfig."""

import pytest

from amr_hub_abm.agent.kinematics import AgentKinematicsConfig
from amr_hub_abm.exceptions import InvalidDefinitionError


@pytest.fixture
def valid_config_data() -> dict[str, object]:
    """Create a config dict containing all required agent kinematics keys."""
    return {
        "agent_movement_speed": 0.001,
        "agent_stochasticity": 5.0,
        "agent_interaction_radius": 0.01,
        "agent_max_movement_attempts": 5,
        "unrelated_key": "ignored",
    }


def test_from_config_builds_expected_values(
    valid_config_data: dict[str, object],
) -> None:
    """Test that from_config reads each field from the corresponding config key."""
    kinematics = AgentKinematicsConfig.from_config(valid_config_data)

    assert kinematics.movement_speed == 0.001
    assert kinematics.stochasticity == 5.0
    assert kinematics.interaction_radius == 0.01
    assert kinematics.max_movement_attempts == 5


def test_from_config_is_frozen(valid_config_data: dict[str, object]) -> None:
    """Test that the resulting AgentKinematicsConfig instance is immutable."""
    kinematics = AgentKinematicsConfig.from_config(valid_config_data)

    with pytest.raises(AttributeError):
        kinematics.movement_speed = 1.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "missing_key",
    [
        "agent_movement_speed",
        "agent_stochasticity",
        "agent_interaction_radius",
        "agent_max_movement_attempts",
    ],
)
def test_from_config_raises_for_missing_key(
    valid_config_data: dict[str, object], missing_key: str
) -> None:
    """Test that a missing required key raises InvalidDefinitionError."""
    del valid_config_data[missing_key]

    with pytest.raises(InvalidDefinitionError) as exc_info:
        AgentKinematicsConfig.from_config(valid_config_data)

    assert missing_key in str(exc_info.value)


def test_from_config_raises_for_empty_config() -> None:
    """Test that an empty config reports all missing keys."""
    with pytest.raises(InvalidDefinitionError) as exc_info:
        AgentKinematicsConfig.from_config({})

    message = str(exc_info.value)
    assert "agent_movement_speed" in message
    assert "agent_stochasticity" in message
    assert "agent_interaction_radius" in message
    assert "agent_max_movement_attempts" in message
