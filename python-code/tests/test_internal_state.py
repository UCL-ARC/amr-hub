"""Tests for agent internal state."""

import pytest

from amr_hub_abm.agent.enums import AgentType
from amr_hub_abm.agent.internal_state import InternalState, InternalStateConfig
from amr_hub_abm.exceptions import InvalidDefinitionError


def test_healthcare_worker_state_includes_fatigue() -> None:
    """Healthcare workers receive all modelled needs."""
    state = InternalState.for_agent_type(
        AgentType.HEALTHCARE_WORKER,
        fatigue=0.2,
        hunger=0.3,
        toilet_need=0.4,
    )

    assert state.fatigue == 0.2
    assert state.hunger == 0.3
    assert state.toilet_need == 0.4


def test_patient_state_excludes_fatigue() -> None:
    """Patients do not receive a fatigue state."""
    state = InternalState.for_agent_type(AgentType.PATIENT, hunger=0.3, toilet_need=0.4)

    assert state.fatigue is None
    assert state.hunger == 0.3
    assert state.toilet_need == 0.4


def test_state_update_is_bounded() -> None:
    """State updates increase needs but never exceed one."""
    state = InternalState(fatigue=0.9, hunger=0.9, toilet_need=0.9)

    state.update(hunger_rate=0.2, toilet_rate=0.2, fatigue_rate=0.2)

    assert state.fatigue == 1.0
    assert state.hunger == 1.0
    assert state.toilet_need == 1.0


def test_invalid_state_level_raises() -> None:
    """Invalid normalized values are rejected."""
    with pytest.raises(InvalidDefinitionError, match="hunger"):
        InternalState(hunger=1.1)


def test_config_updates_state_by_role() -> None:
    """Configured rates are applied only to the needs for each role."""
    config = InternalStateConfig(
        hcw_initial_fatigue=0.0,
        hcw_initial_hunger=0.0,
        hcw_initial_toilet_need=0.0,
        patient_initial_hunger=0.0,
        patient_initial_toilet_need=0.0,
        hcw_fatigue_rate=0.1,
        hcw_hunger_rate=0.2,
        hcw_toilet_rate=0.3,
        patient_hunger_rate=0.4,
        patient_toilet_rate=0.5,
    )
    worker = config.initial_state(AgentType.HEALTHCARE_WORKER)
    patient = config.initial_state(AgentType.PATIENT)

    config.update_state(worker, AgentType.HEALTHCARE_WORKER)
    config.update_state(patient, AgentType.PATIENT)

    assert worker == InternalState(fatigue=0.1, hunger=0.2, toilet_need=0.3)
    assert patient == InternalState(fatigue=None, hunger=0.4, toilet_need=0.5)
