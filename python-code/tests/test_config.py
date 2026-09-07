"""Tests for simulation input configuration."""

from pathlib import Path

import pytest

from amr_hub_abm.config import LocationDataConfig, LocationTimeseriesDataFormat
from amr_hub_abm.exceptions import InvalidDefinitionError


def test_explicit_duckdb_location_data_config() -> None:
    """Test parsing the versioned DuckDB source block."""
    source = LocationDataConfig.from_config(
        {
            "location_data": {
                "format": "duckdb",
                "path": "events.duckdb",
                "table": "events",
                "schema_version": 3,
            }
        }
    )

    assert source.format == LocationTimeseriesDataFormat.DUCKDB
    assert source.path == Path("events.duckdb")
    assert source.table == "events"
    assert source.schema_version == 3


def test_legacy_csv_location_data_config_warns() -> None:
    """Test that the old CSV key remains usable but is deprecated."""
    with pytest.warns(DeprecationWarning, match="deprecated"):
        source = LocationDataConfig.from_config(
            {"location_timeseries_path": "events.csv"}
        )

    assert source.format == LocationTimeseriesDataFormat.CSV
    assert source.path == Path("events.csv")


def test_location_data_config_rejects_ambiguous_sources() -> None:
    """Test that new and legacy source settings cannot both be supplied."""
    config = {
        "location_data": {"format": "duckdb", "path": "events.duckdb"},
        "location_timeseries_path": "events.csv",
    }

    with pytest.raises(InvalidDefinitionError, match="either"):
        LocationDataConfig.from_config(config)


def test_location_data_config_rejects_unknown_format() -> None:
    """Test that only explicitly supported source formats are accepted."""
    with pytest.raises(InvalidDefinitionError, match=r"csv.*duckdb"):
        LocationDataConfig.from_config(
            {"location_data": {"format": "parquet", "path": "events.parquet"}}
        )
