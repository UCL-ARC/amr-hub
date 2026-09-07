"""Module to store configuration parameters for the AMR Hub ABM simulation."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from amr_hub_abm.agent.kinematics import AgentKinematicsConfig
from amr_hub_abm.exceptions import InvalidDefinitionError
from amr_hub_abm.task.task_duration import TaskDurationConfig

if TYPE_CHECKING:
    from collections.abc import Mapping


class LocationTimeseriesDataFormat(StrEnum):
    """Supported location-event input formats."""

    CSV = "csv"
    DUCKDB = "duckdb"


@dataclass(frozen=True)
class LocationDataConfig:
    """Configuration for a location-event data source."""

    format: LocationTimeseriesDataFormat
    path: Path
    table: str = "location_timeseries"
    schema_version: int = 1

    @classmethod
    def from_config(cls, config_data: Mapping[str, object]) -> LocationDataConfig:
        """Build location-event configuration with legacy CSV compatibility."""
        source = config_data.get("location_data")
        legacy_path = config_data.get("location_timeseries_path")

        if source is not None and legacy_path is not None:
            msg = "Use either 'location_data' or 'location_timeseries_path', not both."
            raise InvalidDefinitionError(msg)

        if source is None:
            if not isinstance(legacy_path, str):
                msg = "Missing required 'location_data' configuration."
                raise InvalidDefinitionError(msg)
            warnings.warn(
                "'location_timeseries_path' is deprecated; use 'location_data'.",
                DeprecationWarning,
                stacklevel=2,
            )
            return cls(format=LocationTimeseriesDataFormat.CSV, path=Path(legacy_path))

        if not isinstance(source, dict):
            msg = "'location_data' must be a mapping."
            raise InvalidDefinitionError(msg)

        format_value = source.get("format")
        path_value = source.get("path")
        table_value = source.get("table", "location_timeseries")
        version_value = source.get("schema_version", 1)

        if not isinstance(format_value, str):
            msg = "'location_data.format' must be 'csv' or 'duckdb'."
            raise InvalidDefinitionError(msg)
        try:
            data_format = LocationTimeseriesDataFormat(format_value)
        except ValueError as exc:
            msg = "'location_data.format' must be 'csv' or 'duckdb'."
            raise InvalidDefinitionError(msg) from exc

        if not isinstance(path_value, str) or not path_value:
            msg = "'location_data.path' must be a non-empty string."
            raise InvalidDefinitionError(msg)
        if not isinstance(table_value, str) or not table_value:
            msg = "'location_data.table' must be a non-empty string."
            raise InvalidDefinitionError(msg)
        if (
            isinstance(version_value, bool)
            or not isinstance(version_value, int)
            or version_value < 1
        ):
            msg = "'location_data.schema_version' must be a positive integer."
            raise InvalidDefinitionError(msg)

        return cls(
            format=data_format,
            path=Path(path_value),
            table=table_value,
            schema_version=version_value,
        )


@dataclass(frozen=True)
class SimulationConfig:
    """
    Configuration parameters for the AMR Hub ABM simulation.

    Parameters
    ----------
    agent_kinematics : AgentKinematicsConfig
        Configuration parameters for agent kinematics.
    task_durations : TaskDurationConfig
        Configuration parameters for task durations.

    """

    agent_kinematics: AgentKinematicsConfig
    task_durations: TaskDurationConfig
    location_data: LocationDataConfig
    config_data: Mapping[str, object]

    @classmethod
    def from_file(cls, config_path: Path) -> SimulationConfig:
        """
        Load simulation configuration from a YAML file.

        Parameters
        ----------
        config_path : Path
            Path to the YAML configuration file.

        Returns
        -------
        SimulationConfig
            The simulation configuration parameters.

        """
        with Path.open(config_path, "r", encoding="utf-8") as file:
            config_data = yaml.safe_load(file)

        agent_kinematics = AgentKinematicsConfig.from_config(config_data)
        task_durations = TaskDurationConfig.from_config(config_data)
        location_data = LocationDataConfig.from_config(config_data)

        return cls(
            agent_kinematics=agent_kinematics,
            task_durations=task_durations,
            location_data=location_data,
            config_data=config_data,
        )


sim_config = SimulationConfig.from_file(Path("tests/inputs/simulation_config.yml"))
