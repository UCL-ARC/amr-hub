"""Module for testing the simulation factory."""

from pathlib import Path

import pandas as pd
import pytest

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.simulation_factory import create_simulation, parse_location_timeseries
from amr_hub_abm.space.room import Room


def test_successful_simulation_creation() -> None:
    """Test successful creation of a simulation instance."""
    config_path = Path("tests/inputs/simulation_config.yml")
    simulation = create_simulation(config_path)
    assert simulation is not None


def test_missing_config_file() -> None:
    """Test that FileNotFoundError is raised for a missing config file."""
    missing_config_path = Path("non_existent_config.yml")

    with pytest.raises(FileNotFoundError) as exc_info:
        create_simulation(missing_config_path)

    assert str(exc_info.value) == f"Configuration file not found: {missing_config_path}"


def test_missing_location_timeseries_file() -> None:
    """Test that FileNotFoundError is raised for a missing config file."""
    missing_config_path = Path("tests/inputs/incorrect/simulation_config.yml")

    with pytest.raises(FileNotFoundError) as exc_info:
        create_simulation(missing_config_path)

    assert (
        str(exc_info.value)
        == "Location time series file not found: tests/inputs/non_existent.csv"
    )


def test_invalid_room_in_location_timeseries() -> None:
    """Test that error is raised for an invalid room in location timeseries."""
    config_path = Path("tests/inputs/incorrect/simulation_config_invalid_room.yml")

    with pytest.raises(SimulationModeError) as exc_info:
        create_simulation(config_path)

    assert "Room not found" in str(exc_info.value)


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
            time_step_minutes=15,
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
            time_step_minutes=15,
        )

    assert "Unknown event type" in str(exc_info.value)
