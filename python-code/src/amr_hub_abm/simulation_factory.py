"""Module for creating simulation instances."""

import logging
from pathlib import Path

import pandas as pd
import yaml

from amr_hub_abm.agent import Agent, AgentType
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.read_space_input import SpaceInputReader
from amr_hub_abm.simulation import Simulation, SimulationMode
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


def create_simulation(config_file: Path) -> Simulation:
    """
    Create a simulation instance from a configuration file.

    Args:
        config_file (Path): Path to the configuration file.

    Returns:
        Simulation: An instance of the Simulation class.

    """
    if not config_file.exists():
        msg = f"Configuration file not found: {config_file}"
        raise FileNotFoundError(msg)

    with config_file.open(encoding="utf-8") as file:
        config_data = yaml.safe_load(file)

    buildings_path = Path(config_data["buildings_path"])
    msg = f"Buildings path from config: {buildings_path}"
    logger.debug(msg)
    space_reader = SpaceInputReader(buildings_path)
    logger.debug("Buildings loaded successfully.")
    logger.debug(space_reader.buildings)

    start_time = pd.to_datetime(config_data["start_time"])
    time_step_minutes = config_data["time_step_minutes"]
    end_time = pd.to_datetime(config_data["end_time"])
    total_minutes = (end_time - start_time).total_seconds() / 60
    total_steps = int(total_minutes // time_step_minutes)
    logger.info("Total simulation time steps: %d", total_steps)

    agents = parse_location_timeseries(
        file_path=Path(config_data["location_timeseries_path"]),
        rooms=space_reader.rooms,
        start_time=start_time,
        time_step_minutes=time_step_minutes,
    )
    msg = f"Parsed {len(agents)} agents from location time series."
    logger.info(msg)
    logger.info("Simulation creation complete.")

    return Simulation(
        name="AMR Hub ABM Simulation",
        description="A simulation instance created from configuration.",
        mode=SimulationMode.SPATIAL,
        space=space_reader.buildings,
        agents=agents,
        total_simulation_time=total_steps,
    )


def parse_location_string(location_str: str) -> tuple[str, int, str]:
    """
    Parse a location string into its components.

    Args:
        location_str (str): The location string in the format "BuildingName:x,y".

    Returns:
        tuple[str, int, str]: A tuple containing the building name, floor number,
        and room name.

    """
    building_part, floor, room = location_str.split(":")
    return building_part, int(floor), room


def update_patient(
    patient_id: int,
    building: str,
    floor: int,
    room: Room,
    patient_dict: dict[int, Agent],
) -> None:
    """Update patient information from data."""
    if patient_id is not None and patient_id not in patient_dict:
        patient_point = room.get_random_point()
        location = Location(
            building=building,
            floor=floor,
            x=patient_point[0],
            y=patient_point[1],
        )

        patient_dict[patient_id] = Agent(
            idx=patient_id,
            location=location,
            heading=0.0,
            agent_type=AgentType.PATIENT,
        )


def update_hcw(
    hcw_id: int,
    location: Location,
    timestep_index: int,
    hcw_dict: dict[int, Agent],
) -> None:
    """Update healthcare worker information from data."""
    if hcw_id in hcw_dict:
        hcw_dict[hcw_id].data_location_time_series.append((timestep_index, location))
    else:
        hcw_dict[hcw_id] = Agent(
            idx=hcw_id,
            location=location,
            heading=0.0,
            agent_type=AgentType.HEALTHCARE_WORKER,
        )
        hcw_dict[hcw_id].data_location_time_series.append((timestep_index, location))


def parse_location_timeseries(
    file_path: Path,
    rooms: list[Room],
    start_time: pd.Timestamp,
    time_step_minutes: int,
) -> list[Agent]:
    """
    Parse a CSV file containing location time series data for agents.

    Args:
        file_path (Path): Path to the CSV file.

    Returns:
        list[Agent]: A list of Agent instances with populated location time series.

    """
    if not file_path.exists():
        msg = f"Location time series file not found: {file_path}"
        raise FileNotFoundError(msg)

    df = pd.read_csv(file_path)

    hcw_dict: dict[int, Agent] = {}
    patient_dict: dict[int, Agent] = {}

    for _, row in df.iterrows():
        hcw_id = int(row["hcw_id"])
        timestamp = row["timestamp"]
        location_str = row["location"]
        patient_id = int(row["patient_id"]) if row["patient_id"] != "-" else None

        timestep = pd.to_datetime(timestamp)
        timestep_index = timestamp_to_timestep(timestep, start_time, time_step_minutes)
        building, floor, room_str = parse_location_string(location_str)

        room = next(
            (
                r
                for r in rooms
                if r.name == room_str and r.building == building and r.floor == floor
            ),
            None,
        )

        if room is None:
            msg = f"Room not found: {room_str} in building {building} on floor {floor}"
            raise SimulationModeError(msg)

        point = room.get_random_point()

        location = Location(
            building=building,
            floor=floor,
            x=point[0],
            y=point[1],
        )

        update_hcw(
            hcw_id=hcw_id,
            location=location,
            timestep_index=timestep_index,
            hcw_dict=hcw_dict,
        )

        if patient_id:
            update_patient(
                patient_id=patient_id,
                building=building,
                floor=floor,
                room=room,
                patient_dict=patient_dict,
            )

    return list(hcw_dict.values()) + list(patient_dict.values())


def timestamp_to_timestep(
    timestamp: pd.Timestamp,
    start_time: pd.Timestamp,
    time_step_minutes: int,
) -> int:
    """
    Convert a timestamp to a simulation time step index.

    Args:
        timestamp (pd.Timestamp): The timestamp to convert.
        start_time (pd.Timestamp): The simulation start time.
        time_step_minutes (int): The duration of each time step in minutes.

    Returns:
        int: The corresponding time step index.

    """
    delta = timestamp - start_time
    total_minutes = delta.total_seconds() / 60
    return int(total_minutes // time_step_minutes)
