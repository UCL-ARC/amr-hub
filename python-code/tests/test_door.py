"""Module for testing the Door class functionality."""

import pytest

from amr_hub_abm.exceptions import InvalidDoorError
from amr_hub_abm.space.door import Door


def test_door_creation_with_valid_coordinates() -> None:
    """Test creating a Door with valid start and end coordinates."""
    door = Door(
        open=True,
        connecting_rooms=(101, 102),
        access_control=(True, False),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    assert door.door_hash is not None
    assert door.start == (0.0, 0.0)
    assert door.end == (1.0, 0.0)


def test_door_creation_with_name_only() -> None:
    """Test creating a Door with only a name."""
    door = Door(
        open=False,
        connecting_rooms=(201, 202),
        access_control=(False, True),
        name="Main Entrance",
    )
    assert door.door_hash is not None
    assert door.start is None
    assert door.end is None


def test_door_creation_same_start_and_end_coordinates_raises() -> None:
    """Test that invalid door coordinates raise an InvalidDoorError."""
    with pytest.raises(InvalidDoorError) as excinfo:
        Door(
            open=True,
            connecting_rooms=(301, 302),
            access_control=(True, True),
            start=(1.0, 1.0),
            end=(1.0, 1.0),
        )
    assert "Door start and end points cannot be the same." in str(excinfo.value)


def test_door_creation_missing_coordinates_and_name_raises() -> None:
    """Test that missing coordinates and name raise an InvalidDoorError."""
    with pytest.raises(InvalidDoorError) as excinfo:
        Door(
            open=False,
            connecting_rooms=(401, 402),
            access_control=(False, False),
        )
    assert "Door must have a name if start and end points are not defined." in str(
        excinfo.value
    )


def test_invalid_door_one_coordinate_none_raises() -> None:
    """Test that having one coordinate as None raises an InvalidDoorError."""
    with pytest.raises(InvalidDoorError) as excinfo:
        Door(
            open=True,
            connecting_rooms=(501, 502),
            access_control=(True, False),
            start=(0.0, 0.0),
            end=None,
        )
    assert "Both start and end points must be None or both must be defined." in str(
        excinfo.value
    )


def test_door_equality() -> None:
    """Test equality comparison between two Door instances."""
    door1 = Door(
        open=True,
        connecting_rooms=(601, 602),
        access_control=(True, True),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    door2 = Door(
        open=False,
        connecting_rooms=(601, 602),
        access_control=(False, False),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    assert door1 == door2


def test_door_inequality() -> None:
    """Test inequality comparison between two Door instances."""
    door1 = Door(
        open=True,
        connecting_rooms=(801, 802),
        access_control=(True, True),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    door2 = Door(
        open=True,
        connecting_rooms=(803, 804),
        access_control=(True, True),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    assert door1 != door2


def test_invalid_door_equality_with_different_type() -> None:
    """Test that comparing Door with a different type returns NotImplemented."""
    door = Door(
        open=True,
        connecting_rooms=(1001, 1002),
        access_control=(True, True),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    assert door.__eq__("not a door") is False


def test_door_hash_consistency() -> None:
    """Test that the hash of a Door instance is consistent."""
    door = Door(
        open=True,
        connecting_rooms=(1101, 1102),
        access_control=(True, False),
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    first_hash = hash(door)
    second_hash = hash(door)
    assert first_hash == second_hash


def test_door_invalid_name_hash_raises() -> None:
    """Test that a name-based hash without a name raises an InvalidDoorError."""
    door = Door(
        open=False,
        connecting_rooms=(1201, 1202),
        access_control=(False, True),
        start=(0, 0),
        end=(1, 0),
    )
    with pytest.raises(InvalidDoorError) as excinfo:
        door.create_name_hash()
    assert "Door name must be defined to create name-based hash." in str(excinfo.value)


def test_invalid_door_line_property_raises() -> None:
    """Test that accessing line property with undefined coordinates raises an error."""
    door = Door(
        open=True,
        connecting_rooms=(1301, 1302),
        access_control=(True, True),
        name="Side Door",
    )
    with pytest.raises(InvalidDoorError) as excinfo:
        _ = door.line
    assert "Door start and end must be defined when not in topological mode." in str(
        excinfo.value
    )
