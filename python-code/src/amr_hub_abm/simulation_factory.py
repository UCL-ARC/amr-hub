"""Module for creating simulation instances."""

import logging
from pathlib import Path

import yaml

from amr_hub_abm.agent import Agent
from amr_hub_abm.read_space_input import SpaceInputReader
from amr_hub_abm.simulation import Simulation, SimulationMode
from amr_hub_abm.space.location import Location

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
    with config_file.open(encoding="utf-8") as file:
        config_data = yaml.safe_load(file)

    buildings_path = Path(config_data["buildings_path"])
    msg = f"Buildings path from config: {buildings_path}"
    logger.debug(msg)
    space_reader = SpaceInputReader(buildings_path)
    logger.debug("Buildings loaded successfully.")
    logger.debug(space_reader.buildings)

    agents = [
        Agent(
            idx=1,
            location=Location(building="BuildingA", floor=1, x=1.0, y=1.0),
            heading=0.0,
        )
    ]

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


if __name__ == "__main__":
    config_path = Path("src/amr_hub_abm/simulation_config.yml")
    simulation = create_simulation(config_path)
