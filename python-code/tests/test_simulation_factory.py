"""Module for testing the simulation factory."""

import numpy as np
import pandas as pd
import pytest

from amr_hub_abm.agent.kinematics import AgentKinematicsConfig
from amr_hub_abm.config import sim_config
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.simulation_factory import create_simulation, parse_location_timeseries
from amr_hub_abm.space.room import Room


def test_successful_simulation_creation() -> None:
    """Test successful creation of a simulation instance."""
    simulation = create_simulation(sim_config)
    assert simulation is not None


@pytest.fixture
def sample_room() -> Room:
    """Create a sample Room for testing."""
    return Room(
        room_id=101,
        name="Room101",
        building="BuildingA",
        floor=1,
        contents=[],
        doors=[],
        walls=[],
        area=100.0,
        rng_generator=np.random.default_rng(),
    )


@pytest.fixture
def location_timeseries_df() -> pd.DataFrame:
    """Create a sample location timeseries DataFrame for testing."""
    return pd.DataFrame(
        {
            "hcw_id": [1],
            "timestamp": ["2023-01-01 08:00:00"],
            "location": ["BuildingA:1:Room101"],
            "patient_id": ["-"],
            "event_type": ["attend_patient"],
            "door_id": ["-"],
        }
    )


def test_missing_patient_id_in_location_timeseries(
    sample_room: Room, location_timeseries_df: pd.DataFrame
) -> None:
    """Test that error is raised for a missing patient ID in location timeseries."""
    df = location_timeseries_df.copy()
    with pytest.raises(SimulationModeError) as exc_info:
        parse_location_timeseries(
            timeseries_data=df,
            rooms=[sample_room],
            start_time=pd.Timestamp("2023-01-01 08:00:00"),
            total_time_steps=4,
            time_scaling_factor=60,
            rng_generator=np.random.default_rng(),
            agent_kinematics=AgentKinematicsConfig(
                movement_speed=0.001,
                stochasticity=0.0,
                interaction_radius=0.01,
                max_movement_attempts=5,
            ),
            task_durations=sim_config.task_durations,
        )

    assert "Patient ID must be provided" in str(exc_info.value)


def test_location_timeseries_invalid_event_type(
    sample_room: Room, location_timeseries_df: pd.DataFrame
) -> None:
    """Test that error is raised for an invalid event type in location timeseries."""
    df = location_timeseries_df.copy()
    df.loc[0, "event_type"] = "invalid_event"

    with pytest.raises(SimulationModeError) as exc_info:
        parse_location_timeseries(
            timeseries_data=df,
            rooms=[sample_room],
            start_time=pd.Timestamp("2023-01-01 08:00:00"),
            total_time_steps=4,
            time_scaling_factor=60,
            rng_generator=np.random.default_rng(),
            agent_kinematics=AgentKinematicsConfig(
                movement_speed=0.001,
                stochasticity=0.0,
                interaction_radius=0.01,
                max_movement_attempts=5,
            ),
            task_durations=sim_config.task_durations,
        )

    assert "Unknown event type" in str(exc_info.value)
