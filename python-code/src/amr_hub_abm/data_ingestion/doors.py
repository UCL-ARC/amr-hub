"""Extract canonical AMR-Hub room codes from door descriptions."""

import re
from dataclasses import dataclass

import pandas as pd

_LOCATION_PREFIX = re.compile(
    r"^\s*(?P<building>[A-Z0-9]+)\s+(?P<floor>\d+)(?:ST|ND|RD|TH)\s+FLR\b",
    re.IGNORECASE,
)
_FULL_ROOM_CODE = re.compile(
    r"\b(?P<room_code>[A-Z]\d{2}[A-Z]{2}\d{3})\b", re.IGNORECASE
)
_SHORT_ROOM_CODE = re.compile(
    r"\b(?P<room_code>[A-Z]{2}\d{2,3})(?:[A-Z])?\b", re.IGNORECASE
)


@dataclass(frozen=True)
class DoorLocation:
    """Canonical location fields extracted from one door description."""

    building: str | None
    floor: int | None
    room_code: str | None


def extract_door_location(value: str) -> DoorLocation:
    """
    Extract a building, floor, and canonical room code from a door description.

    A description must begin with a building name followed by an ordinal floor and
    ``FLR``, such as ``GFA 2ND FLR``. Long room codes are retained. Short codes
    are expanded using the first initial of the building name and a zero-padded
    floor number.

    Parameters
    ----------
    value : str
        Door description to parse.

    Returns
    -------
    DoorLocation
        Extracted building name, numeric floor, and full room code. All fields
        are ``None`` when the location prefix is absent; ``room_code`` is
        ``None`` when no room code is present.

    """
    match = _LOCATION_PREFIX.search(value)
    if match is None:
        return DoorLocation(building=None, floor=None, room_code=None)

    building = match["building"].upper()
    floor = int(match["floor"])
    description = value[match.end() :].upper()
    full_room = _FULL_ROOM_CODE.search(description)

    if full_room is not None:
        room_code = full_room["room_code"]
    else:
        short_room = _SHORT_ROOM_CODE.search(description)
        room_code = (
            f"{building[0]}{floor:02d}{short_room['room_code']}"
            if short_room is not None
            else None
        )

    return DoorLocation(building=building, floor=floor, room_code=room_code)


def extract_door_location_columns(
    frame: pd.DataFrame,
    input_column: str = "input",
) -> pd.DataFrame:
    """
    Add canonical door-location fields to a copy of a DataFrame.

    Parameters
    ----------
    frame : pandas.DataFrame
        Source data containing door descriptions.
    input_column : str, default="input"
        Name of the column containing door descriptions.

    Returns
    -------
    pandas.DataFrame
        Copy of ``frame`` with ``building``, ``floor``, and ``room_code``
        columns.

    Raises
    ------
    KeyError
        If ``input_column`` is absent from ``frame``.

    """
    if input_column not in frame:
        msg = f"Missing input column: {input_column}"
        raise KeyError(msg)

    locations = [extract_door_location(value) for value in frame[input_column]]
    extracted = pd.DataFrame(
        {
            "building": [location.building for location in locations],
            "floor": [location.floor for location in locations],
            "room_code": [location.room_code for location in locations],
        },
        index=frame.index,
    )
    return frame.join(extracted)
