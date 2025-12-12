"""Module for testing reading space input functionality."""

from pathlib import Path

from amr_hub_abm.read_space_input import SpaceInputReader


def test_successful_reading() -> None:
    """Test successful reading of space input."""
    data = SpaceInputReader(input_path=Path("sample_floor_spatial.yml"))
    floor = data.buildings[0].floors[0]
    assert floor.room_ids == [0, 1, 2]
