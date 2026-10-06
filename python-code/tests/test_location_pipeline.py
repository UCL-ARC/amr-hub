"""Tests for automated roster-filtered location-data preparation."""

from dataclasses import replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from amr_hub_abm.config import (
    LocationTimeseriesDataConfig,
    LocationTimeseriesDataFormat,
    SimulationConfig,
    sim_config,
)
from amr_hub_abm.data_ingestion import (
    EventPreparationStatus,
    RosterFilterStatus,
    build_simulation_location_database,
    build_synthetic_location_inputs,
    prepare_simulation_location_data,
)
from amr_hub_abm.exceptions import InvalidDefinitionError, LocationDataValidationError
from amr_hub_abm.location_data import read_location_timeseries
from amr_hub_abm.simulation_factory import create_simulation


def location_pipeline_config() -> SimulationConfig:
    """Return the normal simulation contract with the pipeline spatial fixture."""
    config_data = dict(sim_config.config_data)
    config_data["buildings_path"] = "tests/inputs/location_pipeline_buildings.yml"
    return replace(sim_config, config_data=config_data)


def location_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create mixed source records with resolved and intentionally excluded rows."""
    inputs = build_synthetic_location_inputs(
        building="BETA",
        floor=8,
        patient_room="B08NN001",
        door_room="B08NN002",
    )
    events = inputs.events.copy()
    events.loc[events["event_type"] == "occupy_content", "event_type"] = "workstation"
    events = pd.concat(
        [
            events,
            pd.DataFrame(
                [
                    {
                        "eventID": "outside-shift",
                        "locationID": "patient-reference",
                        "hcw_id": 1,
                        "timestamp": pd.Timestamp("2024-01-01 12:00:00"),
                        "event_type": "attend_patient",
                        "patient_id": 5,
                        "door_id": pd.NA,
                        "content_type": pd.NA,
                    },
                    {
                        "eventID": "unrostered",
                        "locationID": "door-reference",
                        "hcw_id": 2,
                        "timestamp": pd.Timestamp("2024-01-01 09:05:00"),
                        "event_type": "door_access",
                        "patient_id": pd.NA,
                        "door_id": pd.NA,
                        "content_type": pd.NA,
                    },
                    {
                        "eventID": "outside-window",
                        "locationID": "door-reference",
                        "hcw_id": 1,
                        "timestamp": pd.Timestamp("2024-01-02 12:00:00"),
                        "event_type": "door_access",
                        "patient_id": pd.NA,
                        "door_id": pd.NA,
                        "content_type": pd.NA,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    return (
        events,
        inputs.bed_references,
        inputs.room_code_mappings,
        inputs.door_references,
    )


def roster() -> pd.DataFrame:
    """Return one shift that covers the two initially resolved events."""
    return pd.DataFrame(
        {
            "hcw_id": [1],
            "shift_start": [pd.Timestamp("2024-01-01 08:00:00")],
            "shift_end": [pd.Timestamp("2024-01-01 09:10:00")],
        }
    )


def test_pipeline_filters_events_and_writes_simulator_database(tmp_path: Path) -> None:
    """Resolved, rostered events round-trip through the simulator DuckDB contract."""
    events, bed_references, room_code_mappings, door_references = location_inputs()
    output_path = tmp_path / "prepared-events.duckdb"

    report = build_simulation_location_database(
        events,
        bed_references,
        room_code_mappings,
        door_references,
        roster(),
        location_pipeline_config(),
        output_path,
        patient_building="BETA",
        patient_floor=8,
        rng_generator=np.random.default_rng(0),
    )

    assert report.location_timeseries["event_sequence"].tolist() == [1, 2]
    assert report.audit["resolution_status"].tolist() == [
        "resolved",
        "resolved",
        "reference_not_found",
        "room_not_in_model",
        EventPreparationStatus.WORKSTATION_DEFERRED,
        RosterFilterStatus.OUTSIDE_ROSTERED_SHIFT,
        RosterFilterStatus.HCW_NOT_ROSTERED,
        RosterFilterStatus.OUTSIDE_SIMULATION_WINDOW,
    ]
    database_events = read_location_timeseries(
        LocationTimeseriesDataConfig(
            format=LocationTimeseriesDataFormat.DUCKDB,
            path=output_path,
        )
    )
    assert database_events["event_sequence"].tolist() == [1, 2]

    simulation_config = replace(
        location_pipeline_config(),
        location_data=LocationTimeseriesDataConfig(
            format=LocationTimeseriesDataFormat.DUCKDB,
            path=output_path,
        ),
    )
    simulation = create_simulation(simulation_config)
    assert len(simulation.agents) == 2

    with duckdb.connect(str(output_path), read_only=True) as connection:
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM location_reconciliation_audit"
        ).fetchone()
    assert audit_count == (8,)


def test_pipeline_requires_at_least_one_rostered_resolved_event() -> None:
    """A run with only excluded records cannot create simulator input."""
    events, bed_references, room_code_mappings, door_references = location_inputs()
    empty_roster = roster().iloc[0:0]

    with pytest.raises(
        LocationDataValidationError, match="No resolved location events"
    ):
        prepare_simulation_location_data(
            events,
            bed_references,
            room_code_mappings,
            door_references,
            empty_roster,
            location_pipeline_config(),
            patient_building="BETA",
            patient_floor=8,
            rng_generator=np.random.default_rng(0),
        )


def test_pipeline_rejects_invalid_roster_intervals() -> None:
    """Malformed roster data remains a hard input failure."""
    events, bed_references, room_code_mappings, door_references = location_inputs()
    invalid_roster = roster().assign(shift_end=pd.Timestamp("2024-01-01 08:00:00"))

    with pytest.raises(InvalidDefinitionError, match="increasing shift interval"):
        prepare_simulation_location_data(
            events,
            bed_references,
            room_code_mappings,
            door_references,
            invalid_roster,
            location_pipeline_config(),
            patient_building="BETA",
            patient_floor=8,
            rng_generator=np.random.default_rng(0),
        )
