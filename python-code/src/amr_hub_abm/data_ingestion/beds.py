"""Extract canonical AMR-Hub room codes from bed identifiers."""

import re
from dataclasses import dataclass

import pandas as pd

_BED_IDENTIFIER = re.compile(
    r"^\s*(?P<prefix>NU|NN|CB)(?P<room_number>\d{2})-(?P<bed_number>\d{2})\s*$",
    re.IGNORECASE,
)
_ROOM_CODE_SUFFIX = re.compile(r"^[A-Z]\d{2}(?P<suffix>[A-Z]{2}\d{3})$", re.IGNORECASE)
_PREFIXES = {"NU": "Nursery", "NN": "Nursery", "CB": "Cubicle"}


@dataclass(frozen=True)
class BedLocation:
    """Bed details and canonical room code extracted from one bed identifier."""

    building: str | None
    floor: int | None
    room: str | None
    bed: str | None
    room_code: str | None
    ambiguous_mapping: bool = False


def extract_bed_location(
    value: str,
    room_codes: pd.DataFrame,
    building: str = "E",
    floor: int = 2,
) -> BedLocation:
    """
    Extract bed details and construct a canonical room code.

    Parameters
    ----------
    value : str
        Bed identifier in ``NU##-##``, ``NN##-##``, or ``CB##-##`` form.
    room_codes : pandas.DataFrame
        Lookup data with ``room_name``, ``bed_name``, and ``room_code`` columns.
    building : str, default="E"
        Building name whose first initial forms the canonical room-code prefix.
    floor : int, default=2
        Floor number used in the canonical room code.

    Returns
    -------
    BedLocation
        Parsed room and bed names, together with the canonical room code when
        their lookup entry exists and is unambiguous. Conflicting lookup codes
        leave the room code unset and set ``ambiguous_mapping``.

    Raises
    ------
    KeyError
        If a required lookup column is absent.
    ValueError
        If a lookup room code is not in canonical ``X##XX###`` form.

    """
    required_columns = {"room_name", "bed_name", "room_code"}
    missing_columns = required_columns.difference(room_codes.columns)
    if missing_columns:
        msg = f"Missing room-code columns: {', '.join(sorted(missing_columns))}"
        raise KeyError(msg)

    match = _BED_IDENTIFIER.fullmatch(value)
    if match is None:
        return BedLocation(None, None, None, None, None)

    room = f"{_PREFIXES[match['prefix'].upper()]} {int(match['room_number'])}"
    bed = f"Cot {int(match['bed_number'])}"
    matches = room_codes.loc[
        (room_codes["room_name"] == room) & (room_codes["bed_name"] == bed),
        "room_code",
    ]
    if matches.empty:
        return BedLocation(building, floor, room, bed, None)

    unique_codes: set[str] = set()
    suffix = ""
    for candidate in matches:
        suffix_match = (
            _ROOM_CODE_SUFFIX.fullmatch(candidate)
            if isinstance(candidate, str)
            else None
        )
        if suffix_match is None:
            msg = f"Invalid canonical room code: {candidate}"
            raise ValueError(msg)
        unique_codes.add(candidate.upper())
        suffix = suffix_match["suffix"].upper()

    if len(unique_codes) > 1:
        return BedLocation(building, floor, room, bed, None, ambiguous_mapping=True)

    room_code = f"{building[0].upper()}{floor:02d}{suffix}"
    return BedLocation(building, floor, room, bed, room_code)
