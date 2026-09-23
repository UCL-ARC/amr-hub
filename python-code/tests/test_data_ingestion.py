"""Tests for source location ingestion."""

import pandas as pd
import pytest

from amr_hub_abm.data_ingestion import extract_bed_location, extract_door_location
from amr_hub_abm.data_ingestion.doors import extract_door_location_columns
from amr_hub_abm.data_ingestion.normalise import normalise_door_location_events


def test_extract_door_location_expands_short_room_code() -> None:
    """A short code uses the initial of the full building name."""
    location = extract_door_location("BETA 8TH FLR SERVICE XY777 DOOR")

    assert location.building == "BETA"
    assert location.floor == 8
    assert location.room_code == "B08XY777"


def test_extract_door_location_retains_long_room_code() -> None:
    """A canonical room code is not modified."""
    location = extract_door_location("BETA 8TH FLR B08XY777 SERVICE DOOR")

    assert location.room_code == "B08XY777"


def test_extract_door_location_omits_room_code_when_absent() -> None:
    """A valid prefix without a code retains building and floor details."""
    location = extract_door_location("BETA 8TH FLR CONNECTION DOOR")

    assert location.building == "BETA"
    assert location.floor == 8
    assert location.room_code is None


def test_extract_door_location_columns_requires_input_column() -> None:
    """The DataFrame helper reports the missing source field."""
    with pytest.raises(KeyError, match="Missing input column: door_description"):
        extract_door_location_columns(pd.DataFrame(), "door_description")


def test_normalise_door_location_events_generates_simulation_location() -> None:
    """Parsed values use the event format accepted by the simulation factory."""
    events = pd.DataFrame(
        {
            "door_description": [
                "BETA 8TH FLR SERVICE XY777 DOOR",
                "BETA 8TH FLR CONNECTION DOOR",
            ]
        }
    )

    result = normalise_door_location_events(events, "door_description")

    assert result.loc[0, "location"] == "BETA:8:B08XY777"
    assert pd.isna(result.loc[1, "location"])


def test_extract_bed_location_constructs_room_code() -> None:
    """Bed lookups use the full building name and numeric floor."""
    room_codes = pd.DataFrame(
        {
            "room_name": ["Cubicle 99"],
            "ben_name": ["Cot 88"],
            "room_code": ["Q11ZZ999"],
        }
    )

    location = extract_bed_location("CB99-88", room_codes, building="BETA", floor=8)

    assert location.building == "BETA"
    assert location.floor == 8
    assert location.room_code == "B08ZZ999"
