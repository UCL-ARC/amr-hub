"""Module for testing reading space input functionality."""

from pathlib import Path

import pytest

from amr_hub_abm.exceptions import (
    InvalidDefinitionError,
    InvalidDoorError,
    InvalidRoomError,
)
from amr_hub_abm.read_space_input import SpaceInputReader


@pytest.fixture
def space_input_reader() -> SpaceInputReader:
    """Fixture for SpaceInputReader instance."""
    return SpaceInputReader(input_path=Path("tests/inputs/sample_floor_spatial.yml"))


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


def test_door_with_no_connection() -> None:
    """Test that a door with no connecting rooms raises an error."""
    with pytest.raises(InvalidDoorError) as exc_info:
        SpaceInputReader(
            input_path=Path(
                "tests/inputs/incorrect/incorrect_sample_floor_spatial_doors.yml"
            )
        )
    assert "must connect exactly two rooms." in str(exc_info.value)


def test_missing_building_key() -> None:
    """Test that missing 'building' key raises an error."""
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader(
            input_path=Path("tests/inputs/incorrect/missing_building_key.yml")
        )
    assert "The input data must contain a 'building' key." in str(exc_info.value)


def test_missing_keys_from_building() -> None:
    """Test that missing keys from building raises an error."""
    sample_dict: dict = {}
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader.validate_building_data(sample_dict)
    assert "name" in str(exc_info.value)
    sample_dict["name"] = "Test Building"
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader.validate_building_data(sample_dict)
    assert "address" in str(exc_info.value)
    sample_dict["address"] = "123 Test St"
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader.validate_building_data(sample_dict)
    assert "floors" in str(exc_info.value)
    sample_dict["floors"] = []
    assert SpaceInputReader.validate_building_data(sample_dict) is None


def test_missing_keys_from_floor() -> None:
    """Test that missing keys from floor raises an error."""
    sample_dict: dict = {}
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader.validate_floor_data(sample_dict)
    assert "level" in str(exc_info.value)
    sample_dict["level"] = 0
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader.validate_floor_data(sample_dict)
    assert "rooms" in str(exc_info.value)
    sample_dict["rooms"] = []
    assert SpaceInputReader.validate_floor_data(sample_dict) is None


def test_missing_keys_from_room() -> None:
    """Test that missing keys from room raises an error."""
    sample_dict: dict = {}
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader.validate_room_data(sample_dict)
    assert "name" in str(exc_info.value)
    sample_dict["name"] = 0
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader.validate_room_data(sample_dict)
    assert "doors" in str(exc_info.value)
    sample_dict["doors"] = []
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader.validate_room_data(sample_dict)
    assert "walls" in str(exc_info.value)
    sample_dict["walls"] = []
    assert SpaceInputReader.validate_room_data(sample_dict) is None

    sample_dict["area"] = 50.0
    with pytest.raises(KeyError) as exc_info:
        SpaceInputReader.validate_room_data(sample_dict)
    assert "A topological room cannot have walls defined" in str(exc_info.value)

    sample_dict.pop("walls")
    with pytest.raises(NotImplementedError) as exc_info:
        SpaceInputReader.validate_room_data(sample_dict)
    assert "Topological room validation is not yet implemented." in str(exc_info.value)


def test_invalid_wall_data() -> None:
    """Test that invalid wall data raises an error."""
    invalid_wall_data = (0, 0, 5)  # Should be 4 values: x1, y1, x2, y2
    with pytest.raises(InvalidRoomError) as exc_info:
        SpaceInputReader.check_tuple_length(
            invalid_wall_data,  # type: ignore[arg-type]
            data_type="wall",
            expected_length=4,
        )
    assert "Each wall must be defined by 4 values." in str(exc_info.value)

    invalid_door_data = (0, 5, 5)  # Should be 4 values: x1, y1, x2, y2
    with pytest.raises(InvalidDoorError) as exc_info:
        SpaceInputReader.check_tuple_length(
            invalid_door_data,  # type: ignore[arg-type]
            data_type="door",
            expected_length=4,
        )
    assert "Each door must be defined by 4 values." in str(exc_info.value)

    with pytest.raises(InvalidDefinitionError) as exc_info:
        SpaceInputReader.check_tuple_length(
            invalid_wall_data,  # type: ignore[arg-type]
            data_type="invalid_type",
            expected_length=4,
        )
    assert "data_type must be either 'wall' or 'door'." in str(exc_info.value)
