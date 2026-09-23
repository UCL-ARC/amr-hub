"""Tests for versioned location-event input loading and validation."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from amr_hub_abm.config import (
    LocationTimeseriesDataConfig,
    LocationTimeseriesDataFormat,
    sim_config,
)
from amr_hub_abm.exceptions import LocationDataValidationError
from amr_hub_abm.location_data import (
    CANONICAL_COLUMNS,
    read_location_timeseries,
    validate_location_timeseries,
)


def test_duckdb_and_legacy_csv_have_equivalent_events() -> None:
    """Test that both supported formats normalize to the same event values."""
    duckdb_data = read_location_timeseries(sim_config.location_data)
    csv_data = read_location_timeseries(
        LocationTimeseriesDataConfig(
            format=LocationTimeseriesDataFormat.CSV,
            path=Path("tests/inputs/location_timeseries.csv"),
        )
    )

    assert tuple(duckdb_data.columns) == CANONICAL_COLUMNS
    assert len(duckdb_data) == 42
    pd.testing.assert_frame_equal(duckdb_data, csv_data)


def test_duckdb_event_sequence_resolves_timestamp_ties() -> None:
    """Test that tied events retain their explicit sequence order."""
    data = read_location_timeseries(sim_config.location_data)
    tied = data[
        (data["hcw_id"] == 2)
        & (data["timestamp"] == pd.Timestamp("2024-01-01 14:00:00"))
    ]

    assert tied["event_sequence"].tolist() == [32, 33]
    assert tied["event_type"].tolist() == ["attend_patient", "door_access"]


def test_duckdb_accepts_location_event_view(tmp_path: Path) -> None:
    """Test that a trusted view can provide the location-event relation."""
    database_path = tmp_path / "view_source.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            "CREATE TABLE amr_hub_schema "
            "(component VARCHAR PRIMARY KEY, schema_version INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO amr_hub_schema VALUES ('location_timeseries', 1)"
        )
        connection.execute(
            """
            CREATE TABLE source_events (
                event_sequence BIGINT,
                hcw_id INTEGER,
                timestamp TIMESTAMP,
                location VARCHAR,
                event_type VARCHAR,
                patient_id INTEGER,
                door_id INTEGER,
                content_type INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO source_events VALUES
            (1, 1, '2024-01-01 00:00:00', 'A:0:Room 1',
             'goto_location', NULL, NULL, NULL)
            """
        )
        connection.execute(
            "CREATE VIEW location_timeseries AS SELECT * FROM source_events"
        )

    source = LocationTimeseriesDataConfig(
        format=LocationTimeseriesDataFormat.DUCKDB,
        path=database_path,
    )
    data = read_location_timeseries(source)

    assert len(data) == 1
    assert data.loc[0, "hcw_id"] == 1


def test_events_are_ordered_globally_by_timestamp() -> None:
    """Test that events retain deterministic global chronological order."""
    data = read_location_timeseries(sim_config.location_data)
    ordering = (
        data[["timestamp", "event_sequence", "hcw_id"]].to_records(index=False).tolist()
    )

    assert ordering == sorted(ordering)


def test_duckdb_schema_version_mismatch_is_rejected(tmp_path: Path) -> None:
    """Test that the configured and stored schema versions must agree."""
    database_path = tmp_path / "wrong_version.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            "CREATE TABLE amr_hub_schema "
            "(component VARCHAR PRIMARY KEY, schema_version INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO amr_hub_schema VALUES ('location_timeseries', 2)"
        )

    source = LocationTimeseriesDataConfig(
        format=LocationTimeseriesDataFormat.DUCKDB,
        path=database_path,
        schema_version=1,
    )
    with pytest.raises(LocationDataValidationError, match="version mismatch"):
        read_location_timeseries(source)


def test_duckdb_collects_metadata_and_column_errors(tmp_path: Path) -> None:
    """Test that independent database contract errors are reported together."""
    database_path = tmp_path / "bad_contract.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute("CREATE TABLE location_timeseries (hcw_id VARCHAR)")

    source = LocationTimeseriesDataConfig(
        format=LocationTimeseriesDataFormat.DUCKDB,
        path=database_path,
    )
    with pytest.raises(LocationDataValidationError) as exc_info:
        read_location_timeseries(source)

    assert "metadata table" in str(exc_info.value)
    assert "Missing required column 'timestamp'" in str(exc_info.value)
    assert "Column 'hcw_id' must be INTEGER" in str(exc_info.value)


def test_validation_collects_all_errors() -> None:
    """Test that preflight reports multiple bad values in a single pass."""
    data = pd.DataFrame(
        [
            {
                "event_sequence": 1,
                "hcw_id": 0,
                "timestamp": pd.Timestamp("2025-01-01"),
                "location": "Unknown:0:Nowhere",
                "event_type": "unknown_event",
                "patient_id": 4,
                "door_id": pd.NA,
                "content_type": pd.NA,
            }
        ],
        columns=CANONICAL_COLUMNS,
    )

    report = validate_location_timeseries(
        data=data,
        rooms=[],
        start_time=pd.Timestamp("2024-01-01"),
        end_time=pd.Timestamp("2024-01-02"),
        task_durations=sim_config.task_durations,
    )

    assert len(report.errors) >= 4
    with pytest.raises(LocationDataValidationError) as exc_info:
        report.raise_for_errors()
    assert "hcw_id" in str(exc_info.value)
    assert "outside the simulation window" in str(exc_info.value)
    assert "unsupported event_type" in str(exc_info.value)
    assert "not in the building model" in str(exc_info.value)
