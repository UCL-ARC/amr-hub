"""Tests for synthetic event-location inputs."""

import pytest

from amr_hub_abm.data_ingestion.synthetic_events import (
    build_synthetic_location_inputs,
)
from amr_hub_abm.exceptions import InvalidDefinitionError


def test_build_synthetic_location_inputs_covers_mapping_outcomes() -> None:
    """Synthetic inputs include resolved, missing, ambiguous, and unsupported cases."""
    inputs = build_synthetic_location_inputs(
        building="BETA",
        floor=8,
        patient_room="B08NN012",
        door_room="B08XY777",
        ambiguous_door_room="B08XY778",
    )

    assert inputs.events["eventID"].tolist() == [
        "patient-resolved",
        "door-resolved",
        "reference-missing",
        "room-missing",
        "door-ambiguous",
        "event-unsupported",
    ]
    assert inputs.bed_references.to_dict("records") == [
        {"locationID": "patient-reference", "bedName": "NN12-01"}
    ]
    assert inputs.room_code_mappings.to_dict("records") == [
        {
            "roomCode": "B08NN012",
            "roomName": "Nursery 12",
            "bedName": "Cot 1",
        }
    ]
    assert inputs.door_references["descriptiveDoorName"].tolist() == [
        "BETA 8TH FLR B08XY777 DOOR",
        "BETA 8TH FLR B08ZZ999 DOOR",
        "BETA 8TH FLR B08XY778 DOOR",
    ]


def test_build_synthetic_location_inputs_requires_supported_patient_room() -> None:
    """The generated bed identifier must be compatible with the bed parser."""
    with pytest.raises(InvalidDefinitionError, match="compatible with a synthetic bed"):
        build_synthetic_location_inputs(
            building="BETA",
            floor=8,
            patient_room="B08XY777",
            door_room="B08XY777",
        )
