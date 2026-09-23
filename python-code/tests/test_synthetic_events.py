"""Tests for synthetic event-location inputs."""

from pathlib import Path

import numpy as np
import pytest

from amr_hub_abm.data_ingestion.plotting import plot_location_mapping
from amr_hub_abm.data_ingestion.prepared_events import (
    EventPreparationStatus,
    prepare_location_events,
)
from amr_hub_abm.data_ingestion.reference_locations import (
    EventLocationResolutionStatus,
)
from amr_hub_abm.data_ingestion.synthetic_events import (
    build_synthetic_location_inputs,
)
from amr_hub_abm.exceptions import InvalidDefinitionError
from amr_hub_abm.spatial.door import Door
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.spatial.wall import Wall


def make_room(name: str, doors: list[Door] | None = None) -> Room:
    """Create a synthetic spatial room for preparation tests."""
    coordinates = [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)]
    walls = [
        Wall(start=start, end=end)
        for start, end in zip(
            coordinates,
            [*coordinates[1:], coordinates[0]],
            strict=True,
        )
    ]
    return Room(
        room_id=sum(ord(character) for character in name),
        name=name,
        building="BETA",
        floor=8,
        contents=[],
        doors=[] if doors is None else doors,
        walls=walls,
        rng_generator=np.random.default_rng(),
    )


def test_build_synthetic_location_inputs_covers_mapping_outcomes() -> None:
    """Synthetic inputs include resolved, missing, ambiguous, and unsupported cases."""
    inputs = build_synthetic_location_inputs(
        building="BETA",
        floor=8,
        patient_room="B08NN012",
        door_room="B08NN777",
        ambiguous_door_room="B08NN778",
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
        "BETA 8TH FLR B08NN777 DOOR",
        "BETA 8TH FLR B08NN999 DOOR",
        "BETA 8TH FLR B08NN778 DOOR",
    ]


def test_build_synthetic_location_inputs_requires_nn_patient_room() -> None:
    """The generated bed identifier must use a canonical NN room code."""
    with pytest.raises(InvalidDefinitionError, match="canonical NN room code"):
        build_synthetic_location_inputs(
            building="BETA",
            floor=8,
            patient_room="B08XY777",
            door_room="B08NN777",
        )


@pytest.mark.parametrize(
    ("door_room", "additional_door_rooms", "ambiguous_door_room"),
    [
        ("B08XY777", (), None),
        ("B08NN777", ("B08XY776",), None),
        ("B08NN777", (), "B08XY778"),
    ],
)
def test_build_synthetic_location_inputs_requires_nn_door_rooms(
    door_room: str,
    additional_door_rooms: tuple[str, ...],
    ambiguous_door_room: str | None,
) -> None:
    """Every generated door reference must target a canonical NN room code."""
    with pytest.raises(InvalidDefinitionError, match="canonical NN room code"):
        build_synthetic_location_inputs(
            building="BETA",
            floor=8,
            patient_room="B08NN012",
            door_room=door_room,
            additional_door_rooms=additional_door_rooms,
            ambiguous_door_room=ambiguous_door_room,
        )


def test_build_synthetic_location_inputs_adds_resolved_examples() -> None:
    """Additional room selections produce distinct events and references."""
    inputs = build_synthetic_location_inputs(
        building="BETA",
        floor=8,
        patient_room="B08NN012",
        door_room="B08NN777",
        additional_patient_rooms=["B08NN013"],
        additional_door_rooms=["B08NN776"],
    )

    assert inputs.events["eventID"].tolist()[:4] == [
        "patient-resolved",
        "patient-resolved-2",
        "door-resolved",
        "door-resolved-2",
    ]
    assert inputs.bed_references.to_dict("records") == [
        {"locationID": "patient-reference", "bedName": "NN12-01"},
        {"locationID": "patient-reference-2", "bedName": "NN13-02"},
    ]
    assert inputs.door_references.iloc[1].to_dict() == {
        "locationID": "door-reference-2",
        "descriptiveDoorName": "BETA 8TH FLR B08NN776 DOOR",
    }


def test_synthetic_inputs_run_through_preparation_pipeline() -> None:
    """Generated records exercise successful and unresolved preparation paths."""
    unique_door = Door(
        is_open=False,
        access_control=(False, False),
        start=(1.0, 0.0),
        end=(3.0, 0.0),
        connecting_rooms=(1, 2),
        door_id=7,
    )
    ambiguous_doors = [
        Door(
            is_open=False,
            access_control=(False, False),
            start=(1.0, 0.0),
            end=(2.0, 0.0),
            connecting_rooms=(1, 2),
            door_id=8,
        ),
        Door(
            is_open=False,
            access_control=(False, False),
            start=(4.0, 0.5),
            end=(4.0, 1.5),
            connecting_rooms=(1, 3),
            door_id=9,
        ),
    ]
    inputs = build_synthetic_location_inputs(
        building="BETA",
        floor=8,
        patient_room="B08NN012",
        door_room="B08NN777",
        ambiguous_door_room="B08NN778",
    )

    report = prepare_location_events(
        inputs.events,
        inputs.bed_references,
        inputs.room_code_mappings,
        inputs.door_references,
        [
            make_room("B08NN012"),
            make_room("B08NN777", [unique_door]),
            make_room("B08NN778", ambiguous_doors),
        ],
        patient_building="BETA",
        patient_floor=8,
    )

    assert report.location_timeseries["event_sequence"].tolist() == [1, 2]
    assert report.audit["resolution_status"].tolist() == [
        EventLocationResolutionStatus.RESOLVED,
        EventLocationResolutionStatus.RESOLVED,
        EventLocationResolutionStatus.REFERENCE_NOT_FOUND,
        EventLocationResolutionStatus.ROOM_NOT_IN_MODEL,
        EventLocationResolutionStatus.AMBIGUOUS_DOORS,
        EventPreparationStatus.UNSUPPORTED_INTERACTION_TYPE,
    ]


def test_plot_location_mapping_writes_synthetic_overlay(tmp_path: Path) -> None:
    """Resolved synthetic events can be plotted without real floorplan data."""
    door = Door(
        is_open=False,
        access_control=(False, False),
        start=(1.0, 0.0),
        end=(3.0, 0.0),
        connecting_rooms=(1, 2),
        door_id=7,
    )
    rooms = [make_room("B08NN012"), make_room("B08NN777", [door])]
    inputs = build_synthetic_location_inputs(
        building="BETA",
        floor=8,
        patient_room="B08NN012",
        door_room="B08NN777",
    )
    report = prepare_location_events(
        inputs.events,
        inputs.bed_references,
        inputs.room_code_mappings,
        inputs.door_references,
        rooms,
        patient_building="BETA",
        patient_floor=8,
    )
    output_path = tmp_path / "location-mapping.png"

    plot_location_mapping(rooms, report, output_path)

    assert output_path.is_file()
    assert output_path.stat().st_size > 0
