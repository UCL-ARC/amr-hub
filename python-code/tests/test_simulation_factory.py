"""Module for testing the simulation factory."""

from pathlib import Path

import pytest

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.simulation_factory import create_simulation


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
