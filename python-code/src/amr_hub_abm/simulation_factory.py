"""Module for creating simulation instances."""

import logging
from pathlib import Path

import pandas as pd
import yaml

from amr_hub_abm.agent import Agent
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
        total_simulation_time=100,
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

    agents_dict: dict[int, Agent] = {}

    for _, row in df.iterrows():
        hcw_id = row["hcw_id"]
        timestamp = row["timestamp"]
        location_str = row["location"]

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

        if hcw_id not in agents_dict:
            agents_dict[hcw_id] = Agent(
                idx=hcw_id,
                location=location,
                heading=0.0,
            )

        agents_dict[hcw_id].data_location_time_series.append((timestep_index, location))

    return list(agents_dict.values())


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
