"""Construct synthetic source records for location-mapping workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from amr_hub_abm.exceptions import InvalidDefinitionError

_PATIENT_ROOM_CODE = re.compile(
    r"^[A-Z]\d{2}(?P<prefix>NU|NN|CB)(?P<room_number>\d{3})$",
    re.IGNORECASE,
)
_ROOM_NAMES = {"NU": "Nursery", "NN": "Nursery", "CB": "Cubicle"}


@dataclass(frozen=True)
class SyntheticLocationInputs:
    """Synthetic source events and their location reference tables."""

    events: pd.DataFrame
    bed_references: pd.DataFrame
    room_code_mappings: pd.DataFrame
    door_references: pd.DataFrame


def _ordinal_floor(floor: int) -> str:
    """Format a numeric floor using the source door-description convention."""
    if 10 <= floor % 100 <= 20:
        suffix = "TH"
    else:
        suffix = {1: "ST", 2: "ND", 3: "RD"}.get(floor % 10, "TH")
    return f"{floor}{suffix}"


def _door_description(building: str, floor: int, room_code: str) -> str:
    """Construct a synthetic source door description."""
    return f"{building.upper()} {_ordinal_floor(floor)} FLR {room_code.upper()} DOOR"


def build_synthetic_location_inputs(
    *,
    building: str,
    floor: int,
    patient_room: str,
    door_room: str,
    ambiguous_door_room: str | None = None,
) -> SyntheticLocationInputs:
    """
    Build synthetic successful and unresolved event-location records.

    Parameters
    ----------
    building : str
        Canonical model building name used in generated source descriptions.
    floor : int
        Canonical model floor used in generated source descriptions.
    patient_room : str
        Canonical room code for the successfully resolved patient event.
    door_room : str
        Canonical room code for the successfully resolved unique-door event.
    ambiguous_door_room : str or None, optional
        Canonical room code for an event expected to have several model doors.

    Returns
    -------
    SyntheticLocationInputs
        Synthetic source events and in-memory reference tables.

    Raises
    ------
    InvalidDefinitionError
        If the building cannot be represented in a source door description or
        the patient room cannot be represented by the supported bed identifier.

    """
    if not building.isalnum():
        msg = "Synthetic door descriptions require an alphanumeric building name"
        raise InvalidDefinitionError(msg)

    patient_match = _PATIENT_ROOM_CODE.fullmatch(patient_room)
    if patient_match is None:
        msg = f"Patient room is not compatible with a synthetic bed: {patient_room}"
        raise InvalidDefinitionError(msg)

    room_number = int(patient_match["room_number"])
    if room_number > 99:
        msg = f"Synthetic bed identifiers support room numbers up to 99: {patient_room}"
        raise InvalidDefinitionError(msg)

    prefix = patient_match["prefix"].upper()
    source_bed = f"{prefix}{room_number:02d}-01"
    room_name = f"{_ROOM_NAMES[prefix]} {room_number}"

    event_definitions = [
        ("patient-resolved", "patient-reference", "attend_patient", 1, pd.NA),
        ("door-resolved", "door-reference", "door_access", pd.NA, pd.NA),
        ("reference-missing", "missing-reference", "door_access", pd.NA, pd.NA),
        ("room-missing", "unknown-room-reference", "door_access", pd.NA, pd.NA),
    ]
    door_reference_definitions = [
        (
            "door-reference",
            _door_description(building, floor, door_room),
        ),
        (
            "unknown-room-reference",
            _door_description(
                building,
                floor,
                f"{building[0].upper()}{floor:02d}ZZ999",
            ),
        ),
    ]
    if ambiguous_door_room is not None:
        event_definitions.append(
            ("door-ambiguous", "ambiguous-door-reference", "door_access", pd.NA, pd.NA)
        )
        door_reference_definitions.append(
            (
                "ambiguous-door-reference",
                _door_description(building, floor, ambiguous_door_room),
            )
        )
    event_definitions.append(
        ("event-unsupported", "unsupported-reference", "occupy_content", pd.NA, 2)
    )

    timestamps = pd.date_range(
        "2024-01-01 09:00:00",
        periods=len(event_definitions),
        freq="5min",
    )
    events = pd.DataFrame(
        {
            "eventID": [definition[0] for definition in event_definitions],
            "locationID": [definition[1] for definition in event_definitions],
            "hcw_id": [1] * len(event_definitions),
            "timestamp": timestamps,
            "event_type": [definition[2] for definition in event_definitions],
            "patient_id": [definition[3] for definition in event_definitions],
            "door_id": [pd.NA] * len(event_definitions),
            "content_type": [definition[4] for definition in event_definitions],
        }
    )
    bed_references = pd.DataFrame(
        {"locationID": ["patient-reference"], "bedName": [source_bed]}
    )
    room_code_mappings = pd.DataFrame(
        {
            "roomCode": [patient_room.upper()],
            "roomName": [room_name],
            "bedName": ["Cot 1"],
        }
    )
    door_references = pd.DataFrame(
        door_reference_definitions,
        columns=["locationID", "descriptiveDoorName"],
    )
    return SyntheticLocationInputs(
        events=events,
        bed_references=bed_references,
        room_code_mappings=room_code_mappings,
        door_references=door_references,
    )
