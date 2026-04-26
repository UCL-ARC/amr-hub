"""Module for creating simulation instances."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from amr_hub_abm.agent import Agent, AgentType
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.read_space_input import SpaceInputReader
from amr_hub_abm.simulation import Simulation, SimulationMode
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.content import ContentType
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room

logger = logging.getLogger(__name__)


def create_space_from_rooms(rooms: list[Room]) -> list[Building]:
    """Create a list of Building instances from a list of Room instances."""
    building_dict: dict[str, Building] = {}

    for room in rooms:
        if room.building not in building_dict:
            building_dict[room.building] = Building(name=room.building, floors=[])

        if room.floor not in [
            f.floor_number for f in building_dict[room.building].floors
        ]:
            building_dict[room.building].floors.append(
                Floor(floor_number=room.floor, rooms=[room])
            )
        else:
            for floor in building_dict[room.building].floors:
                if floor.floor_number == room.floor:
                    floor.rooms.append(room)
                    break

    raw_buildings = list(building_dict.values())
    return Building.sort_and_number_buildings(raw_buildings)


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

    rng_generator = np.random.default_rng()

    buildings_path = Path(config_data["buildings_path"])
    msg = f"Buildings path from config: {buildings_path}"
    logger.debug(msg)
    space_reader = SpaceInputReader(buildings_path, rng_generator)
    logger.debug("Buildings loaded successfully.")
    logger.debug(space_reader.buildings)

    start_time = pd.to_datetime(config_data["start_time"])
    end_time = pd.to_datetime(config_data["end_time"])
    total_seconds = (end_time - start_time).total_seconds()
    time_step_length_seconds = config_data["length_of_timestep_in_seconds"]
    total_steps = int(total_seconds // time_step_length_seconds)
    print(f"Total simulation time steps: {total_steps}")
    logger.info("Total simulation time steps: %d", total_steps)

    timeseries_data = read_location_timeseries(
        file_path=Path(config_data["location_timeseries_path"])
    )

    agents = parse_location_timeseries(
        timeseries_data=timeseries_data,
        rooms=space_reader.rooms,
        start_time=start_time,
        total_time_steps=total_steps,
        time_scaling_factor=time_step_length_seconds,
        rng_generator=rng_generator,
    )

    for agent in agents:
        for task in agent.tasks:
            msg = f"Agent {agent.agent_type, agent.idx} task: {task.task_type.value} at time step {task.time_due}"
            print(msg)

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
        rng_generator=rng_generator,
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


def get_random_location(room: Room, building: str, floor: int) -> Location:
    """Get a random location within a room."""
    point = room.get_random_point()
    return Location(
        building=building,
        floor=floor,
        x=point[0],
        y=point[1],
    )


def update_patient(  # noqa: PLR0913
    patient_id: int,
    space_tuple: tuple[str, int, Room],
    patient_dict: dict[int, Agent],
    total_time_steps: int,
    space: list[Building],
    rng_generator: np.random.Generator,
) -> None:
    """Update patient information from data."""
    building, floor, room = space_tuple

    if patient_id is not None and patient_id not in patient_dict:
        available_beds = [
            b
            for b in room.contents
            if b.content_type == ContentType.BED and not b.occupied
        ]
        if not available_beds:
            msg = (
                f"No available beds found in room {room.name} for patient {patient_id}."
            )
            msg += " Selecting random location in room instead."
            logger.error(msg)
            location = get_random_location(room, building, floor)
        else:
            bed = available_beds[0]
            bed.occupier_id = (patient_id, AgentType.PATIENT)
            location = bed.location

        patient_dict[patient_id] = Agent(
            idx=patient_id,
            location=location,
            heading_rad=0.0,
            agent_type=AgentType.PATIENT,
            trajectory_length=total_time_steps,
            space=space,
            rng_generator=rng_generator,
        )


def update_hcw(  # noqa: PLR0913
    hcw_id: int,
    space_tuple: tuple[str, int, Room],
    event_tuple: tuple[Location, int, str],
    hcw_dict: dict[int, Agent],
    total_time_steps: int,
    space: list[Building],
    rng_generator: np.random.Generator,
    additional_info: dict | None = None,
) -> None:
    """Update healthcare worker information from data."""
    building, floor, room = space_tuple
    location, timestep_index, event_type = event_tuple

    if hcw_id not in hcw_dict:
        available_chairs = [
            c
            for c in room.contents
            if c.content_type == ContentType.CHAIR and not c.occupied
        ]

        if not available_chairs:
            msg = f"No available chairs found in room {room.name} for HCW {hcw_id}."
            msg += " Selecting random location in room instead."
            logger.error(msg)
            hcw_location = get_random_location(room, building, floor)
        else:
            chair = available_chairs[0]
            chair.occupier_id = (hcw_id, AgentType.HEALTHCARE_WORKER)
            hcw_location = chair.location

        hcw_dict[hcw_id] = Agent(
            idx=hcw_id,
            location=hcw_location,
            heading_rad=0.0,
            agent_type=AgentType.HEALTHCARE_WORKER,
            trajectory_length=total_time_steps,
            space=space,
            rng_generator=rng_generator,
        )

    hcw_dict[hcw_id].add_task(timestep_index, location, event_type, additional_info)


def read_location_timeseries(
    file_path: Path,
) -> pd.DataFrame:
    """
    Read a CSV file containing location time series data for agents.

    Args:
        file_path (Path): Path to the CSV file.

    Returns:
        pd.DataFrame: DataFrame containing the location time series data.

    """
    if not file_path.exists():
        msg = f"Location time series file not found: {file_path}"
        raise FileNotFoundError(msg)

    return pd.read_csv(file_path)


def parse_location_timeseries(  # noqa: PLR0913, PLR0915, PLR0912
    timeseries_data: pd.DataFrame,
    rooms: list[Room],
    start_time: pd.Timestamp,
    total_time_steps: int,
    time_scaling_factor: int,
    rng_generator: np.random.Generator,
) -> list[Agent]:
    """
    Parse a CSV file containing location time series data for agents.

    Args:
        timeseries_data (pd.DataFrame): DataFrame containing the location time series.

    Returns:
        list[Agent]: A list of Agent instances with populated location time series.

    """
    hcw_dict: dict[int, Agent] = {}
    patient_dict: dict[int, Agent] = {}

    for _, row in timeseries_data.iterrows():
        hcw_id = int(row["hcw_id"])
        timestamp = row["timestamp"]
        location_str = row["location"]
        patient_id = int(row["patient_id"]) if row["patient_id"] != "-" else None
        event_type = row["event_type"]
        door_id = int(row["door_id"]) if row["door_id"] != "-" else None

        timestep = pd.to_datetime(timestamp)
        timestep_index = timestamp_to_timestep(timestep, start_time, time_scaling_factor)
        building, floor, room_str = parse_location_string(location_str)
        additional_info: dict[Any, Any] = {}

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

        if event_type == "attend_patient" and patient_id is None:
            msg = f"Patient ID must be provided for 'attend' events. Row: {row}"
            raise SimulationModeError(msg)

        if patient_id:
            update_patient(
                patient_id=patient_id,
                space_tuple=(building, floor, room),
                patient_dict=patient_dict,
                total_time_steps=total_time_steps,
                space=create_space_from_rooms(rooms),
                rng_generator=rng_generator,
            )
            patient = patient_dict[patient_id]

        if event_type == "attend_patient" and patient_id is not None:
            additional_info["patient"] = patient
            location = patient.location

        elif event_type == "door_access":
            if door_id is None:
                msg = f"Door ID must be provided for 'door_access' events. Row: {row}"
                raise SimulationModeError(msg)

            door = next(
                (d for d in room.doors if d.door_id == door_id),
                None,
            )

            if door is None:
                msg = f"Door ID {door_id} not found in room {room.name}. Row: {row}"
                msg += f" Available doors: {[d.door_id for d in room.doors]}"
                raise SimulationModeError(msg)

            midpoint = door.line.interpolate(0.5, normalized=True)
            point = (midpoint.x, midpoint.y)
            additional_info["door"] = door

            destination = next(
                idx for idx in door.connecting_rooms if idx != room.room_id
            )
            additional_info["destination"] = destination

            location = Location(
                building=building,
                floor=floor,
                x=point[0],
                y=point[1],
            )
        elif event_type == "workstation":
            possible_locations = [
                c.position
                for c in room.contents
                if c.content_type == ContentType.WORKSTATION
            ]
            if not possible_locations:
                msg = f"No workstation found in room {room.name} for 'workstation'"
                msg += f" event. Row: {row}. Selecting random location in room instead."
                logger.error(msg)
                possible_locations = [room.get_random_point()]

            location = Location(
                building=building,
                floor=floor,
                x=possible_locations[0][0],
                y=possible_locations[0][1],
            )

        elif event_type == "occupy_content":
            content_type = (
                int(row["content_type"]) if row["content_type"] != "-" else None
            )
            if content_type is None:
                msg = "Content type must be provided for 'occupy_content' events. "
                msg += f"Row: {row}"
                raise SimulationModeError(msg)

            # Dummy location for task assignment; actual location will be determined by
            # the content's location when the task is executed

            location = Location(building=building, floor=floor, x=0, y=0)
            additional_info["content_type"] = content_type
            additional_info["room"] = room

        else:
            msg = f"Unknown event type: {event_type} in row: {row}"
            raise SimulationModeError(msg)

        update_hcw(
            hcw_id=hcw_id,
            space_tuple=(building, floor, room),
            event_tuple=(location, timestep_index, event_type),
            hcw_dict=hcw_dict,
            additional_info=additional_info or None,
            total_time_steps=total_time_steps,
            space=create_space_from_rooms(rooms),
            rng_generator=rng_generator,
        )

    return list(hcw_dict.values()) + list(patient_dict.values())


def timestamp_to_timestep(
    timestamp: pd.Timestamp,
    start_time: pd.Timestamp,
    time_scaling_factor: int,
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
    total_minutes = int(delta.total_seconds() // time_scaling_factor)
    return int(total_minutes)
