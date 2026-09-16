"""Tests for preparing resolved location events for simulator input."""

import numpy as np
import pandas as pd
import pytest

from amr_hub_abm.data_ingestion.prepared_events import (
    SIMULATOR_EVENT_COLUMNS,
    EventPreparationStatus,
    prepare_location_events,
)
from amr_hub_abm.data_ingestion.reference_locations import (
    EventLocationResolutionStatus,
)
from amr_hub_abm.exceptions import InvalidDefinitionError
from amr_hub_abm.spatial.door import Door
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.spatial.wall import Wall


def make_room(name: str, doors: list[Door] | None = None) -> Room:
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


def test_prepare_location_events_builds_input_and_complete_audit() -> None:
    """Resolved events become simulator rows while every source event is audited."""
    door = Door(
        is_open=False,
        access_control=(False, False),
        start=(1.0, 0.0),
        end=(3.0, 0.0),
        connecting_rooms=(1, 2),
        door_id=7,
    )
    events = pd.DataFrame(
        {
            "eventID": ["event-1", "event-2", "event-3", "event-4"],
            "locationID": [101, 102, 999, 103],
            "hcw_id": [4, 4, 4, 4],
            "timestamp": pd.to_datetime(
                [
                    "2024-01-01 09:00:00",
                    "2024-01-01 09:05:00",
                    "2024-01-01 09:10:00",
                    "2024-01-01 09:15:00",
                ]
            ),
            "event_type": [
                "attend_patient",
                "door_access",
                "door_access",
                "occupy_content",
            ],
            "patient_id": [8, pd.NA, pd.NA, pd.NA],
            "door_id": [pd.NA, 999, pd.NA, pd.NA],
            "content_type": [pd.NA, pd.NA, pd.NA, 2],
        }
    )
    bed_references = pd.DataFrame({"locationID": [101], "bedName": ["CB99-88"]})
    room_code_mappings = pd.DataFrame(
        {
            "roomCode": ["Q11ZZ999"],
            "roomName": ["Cubicle 99"],
            "bedName": ["Cot 88"],
        }
    )
    door_references = pd.DataFrame(
        {
            "locationID": [102],
            "descriptiveDoorName": ["BETA 8TH FLR SERVICE XY777 DOOR"],
        }
    )

    result = prepare_location_events(
        events,
        bed_references,
        room_code_mappings,
        door_references,
        [make_room("B08ZZ999"), make_room("B08XY777", [door])],
        patient_building="BETA",
        patient_floor=8,
    )

    assert tuple(result.location_timeseries.columns) == SIMULATOR_EVENT_COLUMNS
    assert result.location_timeseries["event_sequence"].tolist() == [1, 2]
    assert result.location_timeseries["location"].tolist() == [
        "BETA:8:B08ZZ999",
        "BETA:8:B08XY777",
    ]
    assert pd.isna(result.location_timeseries.loc[0, "door_id"])
    assert result.location_timeseries.loc[1, "door_id"] == 7
    assert result.audit["source_event_id"].tolist() == events["eventID"].tolist()
    assert result.audit["event_sequence"].tolist() == [1, 2, 3, 4]
    assert result.audit["resolution_status"].tolist() == [
        EventLocationResolutionStatus.RESOLVED,
        EventLocationResolutionStatus.RESOLVED,
        EventLocationResolutionStatus.REFERENCE_NOT_FOUND,
        EventPreparationStatus.UNSUPPORTED_INTERACTION_TYPE,
    ]


def test_prepare_location_events_requires_unique_source_identifier() -> None:
    """A source identifier cannot link results when it is duplicated."""
    events = pd.DataFrame(
        {
            "eventID": ["event-1", "event-1"],
            "locationID": [1, 2],
            "hcw_id": [4, 4],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "event_type": ["door_access", "door_access"],
            "patient_id": [pd.NA, pd.NA],
            "door_id": [pd.NA, pd.NA],
            "content_type": [pd.NA, pd.NA],
        }
    )

    with pytest.raises(InvalidDefinitionError, match="must be unique"):
        prepare_location_events(
            events,
            pd.DataFrame(columns=["locationID", "bedName"]),
            pd.DataFrame(columns=["roomCode", "roomName", "bedName"]),
            pd.DataFrame(columns=["locationID", "descriptiveDoorName"]),
            [],
            patient_building="BETA",
            patient_floor=8,
        )


def test_prepare_location_events_audits_unsupported_events() -> None:
    """Unsupported events produce an audit row without simulator input."""
    events = pd.DataFrame(
        {
            "eventID": ["event-1"],
            "locationID": [1],
            "hcw_id": [4],
            "timestamp": pd.to_datetime(["2024-01-01"]),
            "event_type": ["occupy_content"],
            "patient_id": [pd.NA],
            "door_id": [pd.NA],
            "content_type": [2],
        }
    )

    result = prepare_location_events(
        events,
        pd.DataFrame(columns=["locationID", "bedName"]),
        pd.DataFrame(columns=["roomCode", "roomName", "bedName"]),
        pd.DataFrame(columns=["locationID", "descriptiveDoorName"]),
        [],
        patient_building="BETA",
        patient_floor=8,
    )

    assert result.location_timeseries.empty
    assert tuple(result.location_timeseries.columns) == SIMULATOR_EVENT_COLUMNS
    assert (
        result.audit.loc[0, "resolution_status"]
        == EventPreparationStatus.UNSUPPORTED_INTERACTION_TYPE
    )
