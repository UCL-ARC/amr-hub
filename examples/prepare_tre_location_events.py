"""
Prepare simulator location events from a configured TRE DuckDB source.

Run from ``python-code`` with a TRE-local YAML configuration. The configuration
contains every site-specific table name, column mapping, interaction label,
path, and approved room-code mapping query; it must not be committed.
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import numpy as np
import yaml

from amr_hub_abm.config import SimulationConfig
from amr_hub_abm.data_ingestion.pipeline import build_simulation_location_database

if TYPE_CHECKING:
    import pandas as pd

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrePreparationConfig:
    """Site-specific mappings and paths required for TRE event preparation."""

    source_db: Path
    simulation_config: Path
    output_db: Path
    patient_building: str
    patient_floor: int
    staffevents_table: str
    interactiontypes_table: str
    department_table: str
    doors_table: str
    staff_patient_id: str
    staff_id: str
    staff_timestamp: str
    staff_interaction_type_id: str
    staff_location_id: str
    staff_shift_id: str
    interaction_type_id: str
    interaction_class: str
    interaction_name: str
    department_location_id: str
    department_bed_name: str
    door_location_id: str
    door_description: str
    flowsheet_class: str
    door_message_class: str
    roster_class: str
    workstation_class: str
    roster_start_interaction_type: str
    roster_end_interaction_type: str
    room_code_mappings_query: str

    @classmethod
    def from_file(cls, path: Path) -> TrePreparationConfig:
        """Load a TRE-local mapping configuration and reject incomplete values."""
        with path.open(encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file)
        if not isinstance(data, dict):
            msg = "TRE preparation configuration must be a YAML mapping."
            raise TypeError(msg)

        return cls(
            source_db=Path(_config_string(data, "paths.source_db")),
            simulation_config=Path(_config_string(data, "paths.simulation_config")),
            output_db=Path(_config_string(data, "paths.output_db")),
            patient_building=_config_string(data, "model.patient_building"),
            patient_floor=_config_positive_int(data, "model.patient_floor"),
            staffevents_table=_config_string(data, "tables.staffevents"),
            interactiontypes_table=_config_string(data, "tables.interactiontypes"),
            department_table=_config_string(data, "tables.department"),
            doors_table=_config_string(data, "tables.doors"),
            staff_patient_id=_config_string(data, "columns.staffevents.patient_id"),
            staff_id=_config_string(data, "columns.staffevents.staff_id"),
            staff_timestamp=_config_string(data, "columns.staffevents.timestamp"),
            staff_interaction_type_id=_config_string(
                data, "columns.staffevents.interaction_type_id"
            ),
            staff_location_id=_config_string(data, "columns.staffevents.location_id"),
            staff_shift_id=_config_string(data, "columns.staffevents.shift_id"),
            interaction_type_id=_config_string(
                data, "columns.interactiontypes.interaction_type_id"
            ),
            interaction_class=_config_string(
                data, "columns.interactiontypes.interaction_class"
            ),
            interaction_name=_config_string(
                data, "columns.interactiontypes.interaction_name"
            ),
            department_location_id=_config_string(
                data, "columns.department.location_id"
            ),
            department_bed_name=_config_string(data, "columns.department.bed_name"),
            door_location_id=_config_string(data, "columns.doors.location_id"),
            door_description=_config_string(data, "columns.doors.description"),
            flowsheet_class=_config_string(data, "interaction_classes.flowsheet"),
            door_message_class=_config_string(data, "interaction_classes.doormessage"),
            roster_class=_config_string(data, "interaction_classes.roster"),
            workstation_class=_config_string(data, "interaction_classes.workstation"),
            roster_start_interaction_type=_config_string(
                data, "roster.start_interaction_type"
            ),
            roster_end_interaction_type=_config_string(
                data, "roster.end_interaction_type"
            ),
            room_code_mappings_query=_config_string(data, "room_code_mappings_query"),
        )


def parse_args() -> argparse.Namespace:
    """Parse the path to a TRE-local mapping configuration."""
    parser = argparse.ArgumentParser(
        description="Prepare roster-filtered simulator events from TRE DuckDB tables."
    )
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def _config_string(data: dict[object, object], path: str) -> str:
    """Read one non-empty string from a nested YAML mapping."""
    value: object = data
    for key in path.split("."):
        if not isinstance(value, dict):
            break
        value = value.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"Configuration value '{path}' must be a non-empty string."
        raise ValueError(msg)
    return value


def _config_positive_int(data: dict[object, object], path: str) -> int:
    """Read one positive integer from a nested YAML mapping."""
    value = _config_value(data, path)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"Configuration value '{path}' must be a positive integer."
        raise ValueError(msg)
    return value


def _config_value(data: dict[object, object], path: str) -> object:
    """Read a nested YAML value, returning None when it is absent."""
    value: object = data
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _quoted_identifier(identifier: str) -> str:
    """Return a DuckDB-safe identifier after rejecting arbitrary SQL text."""
    if IDENTIFIER_PATTERN.fullmatch(identifier) is None:
        msg = f"Invalid DuckDB identifier: {identifier!r}"
        raise ValueError(msg)
    return f'"{identifier}"'


def read_source_inputs(
    config: TrePreparationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read and standardise approved source tables without modifying the source DB."""
    staffevents = _quoted_identifier(config.staffevents_table)
    interactiontypes = _quoted_identifier(config.interactiontypes_table)
    department = _quoted_identifier(config.department_table)
    doors = _quoted_identifier(config.doors_table)
    staff = {
        key: _quoted_identifier(value)
        for key, value in {
            "patient_id": config.staff_patient_id,
            "id": config.staff_id,
            "timestamp": config.staff_timestamp,
            "interaction_type_id": config.staff_interaction_type_id,
            "location_id": config.staff_location_id,
            "shift_id": config.staff_shift_id,
        }.items()
    }
    interaction = {
        key: _quoted_identifier(value)
        for key, value in {
            "id": config.interaction_type_id,
            "class": config.interaction_class,
            "name": config.interaction_name,
        }.items()
    }
    department_location_id = _quoted_identifier(config.department_location_id)
    department_bed_name = _quoted_identifier(config.department_bed_name)
    door_location_id = _quoted_identifier(config.door_location_id)
    door_description = _quoted_identifier(config.door_description)

    with duckdb.connect(str(config.source_db), read_only=True) as connection:
        events = connection.execute(
            f"""
            SELECT
                TRY_CAST(staffevents.{staff["id"]} AS BIGINT) AS hcw_id,
                staffevents.{staff["timestamp"]} AS timestamp,
                staffevents.{staff["location_id"]} AS locationID,
                CASE LOWER(interactiontypes.{interaction["class"]})
                    WHEN LOWER(?) THEN 'attend_patient'
                    WHEN LOWER(?) THEN 'door_access'
                    WHEN LOWER(?) THEN 'workstation'
                END AS event_type,
                CASE
                    WHEN LOWER(interactiontypes.{interaction["class"]}) = LOWER(?)
                    THEN TRY_CAST(staffevents.{staff["patient_id"]} AS BIGINT)
                END AS patient_id,
                CAST(NULL AS BIGINT) AS door_id,
                CAST(NULL AS BIGINT) AS content_type
            FROM {staffevents} AS staffevents
            INNER JOIN {interactiontypes} AS interactiontypes
                ON staffevents.{staff["interaction_type_id"]}
                    = interactiontypes.{interaction["id"]}
            WHERE LOWER(interactiontypes.{interaction["class"]})
                IN (LOWER(?), LOWER(?), LOWER(?))
            """,  # noqa: S608
            [
                config.flowsheet_class,
                config.door_message_class,
                config.workstation_class,
                config.flowsheet_class,
                config.flowsheet_class,
                config.door_message_class,
                config.workstation_class,
            ],
        ).fetch_df()
        roster = connection.execute(
            f"""
            SELECT
                TRY_CAST(staffevents.{staff["id"]} AS BIGINT) AS hcw_id,
                staffevents.{staff["shift_id"]} AS shiftid,
                COUNT(*) AS source_record_count,
                MAX(CASE
                    WHEN interactiontypes.{interaction["name"]} = ?
                    THEN staffevents.{staff["timestamp"]}
                END) AS shift_start,
                MAX(CASE
                    WHEN interactiontypes.{interaction["name"]} = ?
                    THEN staffevents.{staff["timestamp"]}
                END) AS shift_end
            FROM {staffevents} AS staffevents
            INNER JOIN {interactiontypes} AS interactiontypes
                ON staffevents.{staff["interaction_type_id"]}
                    = interactiontypes.{interaction["id"]}
            WHERE LOWER(interactiontypes.{interaction["class"]}) = LOWER(?)
                AND staffevents.{staff["shift_id"]} IS NOT NULL
            GROUP BY staffevents.{staff["id"]}, staffevents.{staff["shift_id"]}
            """,  # noqa: S608
            [
                config.roster_start_interaction_type,
                config.roster_end_interaction_type,
                config.roster_class,
            ],
        ).fetch_df()
        bed_references = connection.execute(
            f"SELECT {department_location_id} AS locationID, "  # noqa: S608
            f"{department_bed_name} AS bedName FROM {department}"
        ).fetch_df()
        door_references = connection.execute(
            f"SELECT {door_location_id} AS locationID, "  # noqa: S608
            f"{door_description} AS descriptiveDoorName FROM {doors}"
        ).fetch_df()
        room_code_mappings = connection.execute(
            config.room_code_mappings_query
        ).fetch_df()

    _validate_roster_pairs(roster)
    return events, bed_references, room_code_mappings, door_references, roster


def _validate_roster_pairs(roster: pd.DataFrame) -> None:
    """Reject roster groups that do not contain one recognised start and end record."""
    invalid = roster.loc[
        roster["hcw_id"].isna()
        | roster["shiftid"].isna()
        | roster["source_record_count"].ne(2)
        | roster["shift_start"].isna()
        | roster["shift_end"].isna(),
        ["hcw_id", "shiftid", "source_record_count", "shift_start", "shift_end"],
    ]
    if invalid.empty:
        return
    msg = f"Invalid roster start/end pairs:\n{invalid.to_string(index=False)}"
    raise ValueError(msg)


def main() -> None:
    """Build the versioned DuckDB location-event database for one simulation run."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = TrePreparationConfig.from_file(parse_args().config)
    inputs = read_source_inputs(config)
    events, bed_references, room_code_mappings, door_references, roster = inputs
    report = build_simulation_location_database(
        events,
        bed_references,
        room_code_mappings,
        door_references,
        roster,
        SimulationConfig.from_file(config.simulation_config),
        config.output_db,
        patient_building=config.patient_building,
        patient_floor=config.patient_floor,
        rng_generator=np.random.default_rng(),
    )
    logger.info(
        "Wrote %s simulator events to %s",
        len(report.location_timeseries),
        config.output_db,
    )
    logger.info(
        "Reconciliation statuses:\n%s",
        report.audit["resolution_status"].value_counts(sort=False).to_string(),
    )


if __name__ == "__main__":
    main()
