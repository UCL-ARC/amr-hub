"""Module for testing the Door class functionality."""

import pytest

from amr_hub_abm.exceptions import InvalidDoorError
from amr_hub_abm.space.door import Door


def test_door_creation_with_valid_coordinates() -> None:
    """Test creating a Door with valid start and end coordinates."""
    door = Door(
        is_open=True,
        connecting_rooms=(101, 102),
        access_control=(True, False),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
        door_id=1,
    )
    assert door.start == (0.0, 0.0)
    assert door.end == (1.0, 0.0)


def test_door_creation_with_name_only() -> None:
    """Test creating a Door with only a name."""
    door = Door(
        is_open=False,
        connecting_rooms=(201, 202),
        access_control=(False, True),
        name="Main Entrance",
        door_id=2,
    )
    assert door.start is None
    assert door.end is None


def test_door_creation_same_start_and_end_coordinates_raises() -> None:
    """Test that invalid door coordinates raise an InvalidDoorError."""
    with pytest.raises(InvalidDoorError) as excinfo:
        Door(
            is_open=True,
            connecting_rooms=(301, 302),
            access_control=(True, True),
            start=(1.0, 1.0),
            end=(1.0, 1.0),
            door_id=3,
        )
    assert "Door start and end points cannot be the same." in str(excinfo.value)


def test_door_creation_missing_coordinates_and_name_raises() -> None:
    """Test that missing coordinates and name raise an InvalidDoorError."""
    with pytest.raises(InvalidDoorError) as excinfo:
        Door(
            is_open=False,
            connecting_rooms=(401, 402),
            access_control=(False, False),
            door_id=4,
        )
    assert "Door must have a name if start and end points are not defined." in str(
        excinfo.value
    )


def test_invalid_door_one_coordinate_none_raises() -> None:
    """Test that having one coordinate as None raises an InvalidDoorError."""
    with pytest.raises(InvalidDoorError) as excinfo:
        Door(
            is_open=True,
            connecting_rooms=(501, 502),
            access_control=(True, False),
            start=(0.0, 0.0),
            end=None,
            door_id=5,
        )
    assert "Both start and end points must be None or both must be defined." in str(
        excinfo.value
    )


def test_door_equality() -> None:
    """Test equality comparison between two Door instances."""
    door1 = Door(
        is_open=True,
        connecting_rooms=(601, 602),
        access_control=(True, True),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
        door_id=6,
    )
    door2 = Door(
        is_open=False,
        connecting_rooms=(601, 602),
        access_control=(False, False),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
        door_id=7,
    )
    assert door1 == door2


def test_door_inequality() -> None:
    """Test inequality comparison between two Door instances."""
    door1 = Door(
        is_open=True,
        connecting_rooms=(801, 802),
        access_control=(True, True),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
        door_id=8,
    )
    door2 = Door(
        is_open=True,
        connecting_rooms=(803, 804),
        access_control=(True, True),
        start=(0.0, 0.0),
        end=(1.5, 0.0),
        door_id=9,
    )
    assert door1 != door2


def test_invalid_door_equality_with_different_type() -> None:
    """Test that comparing Door with a different type returns NotImplemented."""
    door = Door(
        is_open=True,
        connecting_rooms=(1001, 1002),
        access_control=(True, True),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
        door_id=10,
    )

    assert (door == "Not a door") is False


def test_door_hash_consistency() -> None:
    """Test that the hash of a Door instance is consistent."""
    door = Door(
        is_open=True,
        connecting_rooms=(1101, 1102),
        access_control=(True, False),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
        door_id=11,
    )
    first_hash = hash(door)
    second_hash = hash(door)
    assert first_hash == second_hash


def test_invalid_door_line_property_raises() -> None:
    """Test that accessing line property with undefined coordinates raises an error."""
    door = Door(
        is_open=True,
        connecting_rooms=(1301, 1302),
        access_control=(True, True),
        name="Side Door",
        door_id=13,
    )
    with pytest.raises(InvalidDoorError) as excinfo:
        _ = door.line
    assert "Door start and end must be defined when not in topological mode." in str(
        excinfo.value
    )
