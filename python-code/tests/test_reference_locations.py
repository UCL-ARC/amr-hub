"""Tests for event location-key reference resolution."""

import numpy as np
import pandas as pd

from amr_hub_abm.data_ingestion.reference_locations import (
    EventLocationResolutionStatus,
    resolve_door_location_events,
    resolve_patient_location_events,
)
from amr_hub_abm.spatial.door import Door
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.spatial.wall import Wall


def make_room(
    name: str,
    doors: list[Door] | None = None,
) -> Room:
    """Create a synthetic spatial room with optional model doors."""
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
        room_id=1,
        name=name,
        building="BETA",
        floor=8,
        contents=[],
        doors=[] if doors is None else doors,
        walls=walls,
        rng_generator=np.random.default_rng(),
    )


def test_resolve_patient_location_events_prepares_and_reconciles_records() -> None:
    """Bed references resolve known events and retain missing references."""
    events = pd.DataFrame({"eventID": [1, 2], "locationID": [101, 999]})
    bed_references = pd.DataFrame(
        {
            "locationID": [101],
            "roomName": ["CB99"],
            "bedName": ["CB99-88"],
        }
    )
    room_code_mappings = pd.DataFrame(
        {
            "roomCode": ["Q11ZZ999"],
            "roomName": ["Cubicle 99"],
            "bedName": ["Cot 88"],
        }
    )
    room = make_room("B08ZZ999")

    report = resolve_patient_location_events(
        events,
        bed_references,
        room_code_mappings,
        [room],
        building="BETA",
        floor=8,
    )

    assert report.prepared["eventID"].tolist() == [1]
    assert report.prepared.loc[0, "model_room_code"] == "B08ZZ999"
    assert report.prepared.loc[0, "location"] == "BETA:8:B08ZZ999"
    assert report.prepared.loc[0, "x"] == 2.0
    assert report.prepared.loc[0, "y"] == 1.0
    assert report.excluded["eventID"].tolist() == [2]
    assert (
        report.excluded.loc[1, "resolution_status"]
        == EventLocationResolutionStatus.REFERENCE_NOT_FOUND
    )


def test_resolve_door_location_events_prepares_unique_model_door() -> None:
    """A door reference resolves to the midpoint of one model door."""
    door = Door(
        is_open=False,
        access_control=(False, False),
        start=(1.0, 0.0),
        end=(3.0, 0.0),
        connecting_rooms=(1, 2),
        door_id=7,
    )
    events = pd.DataFrame({"eventID": [3], "locationID": [102]})
    door_references = pd.DataFrame(
        {
            "locationID": [102],
            "descriptiveDoorName": ["BETA 8TH FLR SERVICE XY777 DOOR"],
        }
    )

    report = resolve_door_location_events(
        events,
        door_references,
        [make_room("B08XY777", [door])],
    )

    assert report.excluded.empty
    assert report.prepared.loc[0, "model_door_id"] == 7
    assert report.prepared.loc[0, "candidate_door_count"] == 1
    assert report.prepared.loc[0, "x"] == 2.0
    assert report.prepared.loc[0, "y"] == 0.0


def test_resolve_door_location_events_excludes_ambiguous_model_door() -> None:
    """A multi-door room remains in the reconciliation output."""
    doors = [
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
    events = pd.DataFrame({"eventID": [4], "locationID": [103]})
    door_references = pd.DataFrame(
        {
            "locationID": [103],
            "descriptiveDoorName": ["BETA 8TH FLR SERVICE XY778 DOOR"],
        }
    )

    report = resolve_door_location_events(
        events,
        door_references,
        [make_room("B08XY778", doors)],
    )

    assert report.prepared.empty
    assert (
        report.excluded.loc[0, "resolution_status"]
        == EventLocationResolutionStatus.AMBIGUOUS_DOORS
    )
    assert report.excluded.loc[0, "candidate_door_count"] == 2
