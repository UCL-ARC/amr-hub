"""Construct synthetic source records for location-mapping workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from amr_hub_abm.exceptions import InvalidDefinitionError

if TYPE_CHECKING:
    from collections.abc import Sequence

_NN_ROOM_CODE = re.compile(
    r"^[A-Z]\d{2}NN(?P<room_number>\d{3})$",
    re.IGNORECASE,
)


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


def _synthetic_bed_reference(
    room_code: str,
    bed_number: int,
) -> tuple[str, str, str]:
    """Return source bed, room name, and bed name for a canonical room code."""
    patient_match = _NN_ROOM_CODE.fullmatch(room_code)
    if patient_match is None:
        msg = f"Synthetic locations require a canonical NN room code: {room_code}"
        raise InvalidDefinitionError(msg)

    room_number = int(patient_match["room_number"])
    if room_number > 99:
        msg = f"Synthetic bed identifiers support room numbers up to 99: {room_code}"
        raise InvalidDefinitionError(msg)

    return (
        f"NN{room_number:02d}-{bed_number:02d}",
        f"Nursery {room_number}",
        f"Cot {bed_number}",
    )


def _validate_nn_room_code(room_code: str) -> None:
    """Require a canonical NN room code for a synthetic location target."""
    if _NN_ROOM_CODE.fullmatch(room_code) is None:
        msg = f"Synthetic locations require a canonical NN room code: {room_code}"
        raise InvalidDefinitionError(msg)


def build_synthetic_location_inputs(  # noqa: PLR0913
    *,
    building: str,
    floor: int,
    patient_room: str,
    door_room: str,
    ambiguous_door_room: str | None = None,
    additional_patient_rooms: Sequence[str] = (),
    additional_door_rooms: Sequence[str] = (),
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
        Canonical NN room code for the successfully resolved patient event.
    door_room : str
        Canonical NN room code for the successfully resolved unique-door event.
    ambiguous_door_room : str or None, optional
        Canonical NN room code for an event expected to have several model doors.
    additional_patient_rooms : collections.abc.Sequence[str], optional
        Further canonical NN rooms that should receive resolved patient events.
    additional_door_rooms : collections.abc.Sequence[str], optional
        Further canonical NN rooms that should receive resolved door events.

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

    patient_rooms = (patient_room, *additional_patient_rooms)
    door_rooms = (door_room, *additional_door_rooms)
    for room_code in (*patient_rooms, *door_rooms):
        _validate_nn_room_code(room_code)
    if ambiguous_door_room is not None:
        _validate_nn_room_code(ambiguous_door_room)

    event_definitions = []
    bed_reference_definitions = []
    room_code_mapping_definitions = []
    for index, room_code in enumerate(patient_rooms, start=1):
        suffix = "" if index == 1 else f"-{index}"
        reference_id = f"patient-reference{suffix}"
        source_bed, room_name, bed_name = _synthetic_bed_reference(room_code, index)
        event_definitions.append(
            (f"patient-resolved{suffix}", reference_id, "attend_patient", index, pd.NA)
        )
        bed_reference_definitions.append((reference_id, source_bed))
        room_code_mapping_definitions.append((room_code.upper(), room_name, bed_name))

    door_reference_definitions = []
    for index, room_code in enumerate(door_rooms, start=1):
        suffix = "" if index == 1 else f"-{index}"
        reference_id = f"door-reference{suffix}"
        event_definitions.append(
            (f"door-resolved{suffix}", reference_id, "door_access", pd.NA, pd.NA)
        )
        door_reference_definitions.append(
            (reference_id, _door_description(building, floor, room_code))
        )

    event_definitions.extend(
        [
            ("reference-missing", "missing-reference", "door_access", pd.NA, pd.NA),
            ("room-missing", "unknown-room-reference", "door_access", pd.NA, pd.NA),
        ]
    )
    door_reference_definitions.append(
        (
            "unknown-room-reference",
            _door_description(
                building,
                floor,
                f"{building[0].upper()}{floor:02d}NN999",
            ),
        )
    )
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
        bed_reference_definitions,
        columns=["locationID", "bedName"],
    )
    room_code_mappings = pd.DataFrame(
        room_code_mapping_definitions,
        columns=["roomCode", "roomName", "bedName"],
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
