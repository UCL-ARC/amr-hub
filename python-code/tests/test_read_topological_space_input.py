"""Module for testing reading space input functionality."""

from pathlib import Path

import pytest

from amr_hub_abm.exceptions import InvalidDoorError
from amr_hub_abm.read_space_input import SpaceInputReader


@pytest.fixture
def space_input_reader() -> SpaceInputReader:
    """Fixture for SpaceInputReader instance."""
    return SpaceInputReader(
        input_path=Path("tests/inputs/sample_floor_topological.yml")
    )


def test_successful_reading(space_input_reader: SpaceInputReader) -> None:
    """Test successful reading of space input."""
    assert space_input_reader is not None
    assert type(space_input_reader) is SpaceInputReader


def test_buildings_and_floors(space_input_reader: SpaceInputReader) -> None:
    """Test buildings and floors are read correctly."""
    buildings = space_input_reader.buildings
    assert len(buildings) == 1
    building = buildings[0]
    assert building.name == "Sample Hospital"
    assert len(building.floors) == 1
    floor_numbers = [floor.floor_number for floor in building.floors]
    assert floor_numbers == [0]


def test_floor_rooms(space_input_reader: SpaceInputReader) -> None:
    """Test rooms on the floor are read correctly."""
    floor = space_input_reader.buildings[0].floors[0]
    assert len(floor.rooms) == 3  # noqa: PLR2004
    room_ids = [room.room_id for room in floor.rooms]
    assert room_ids == [0, 1, 2]
    assert floor.adjacency_matrix.shape == (3, 3)
    expected_edges = {(0, 2), (1, 2), (2, 1), (2, 0)}
    assert floor.edge_set == expected_edges
    expected_room_names = ["Staff Room", "Ward", "Corridor"]
    assert floor.room_names == expected_room_names
    expected_adjacency = [
        [0, 0, 1],
        [0, 0, 1],
        [1, 1, 0],
    ]
    assert floor.adjacency_matrix.tolist() == expected_adjacency


def test_invalid_topological_room_data() -> None:
    """Test that room data is read correctly."""
    room_data = {
        "name": "Test Room",
        "area": 20,
        "doors": [1, 2],
    }

    with pytest.raises(InvalidDoorError) as exc_info:
        SpaceInputReader.validate_room_data(room_data)

    assert "In topological mode, doors must be defined by their names." in str(
        exc_info.value
    )
