"""Module containing space related functions and of agent."""

import logging
import math

from numpy.random import Generator

from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room

logger = logging.getLogger(__name__)


def get_room(location: Location, rooms: list[Room]) -> Room | None:
    """
    Identify the room in which the given co-ordinates are located.

    Parameters
    ----------
    location : Location
        The location for which the room is to be identified.

    rooms : list[Room]
        The list of rooms to check for the given location.

    Returns
    -------
    Room | None
        The room in which the agent is located, or None if the agent is not located
        in any room.

    """
    for room in rooms:
        if room.building != location.building:
            continue
        if room.floor != location.floor:
            continue

        if room.contains_point((location.x, location.y)):
            return room

    logger.info(
        """
        The given co-ordinates (%s) are not located in any room on floor %d
        of building '%s'.
        """,
        (location.x, location.y),
        location.floor,
        location.building,
    )
    return None


def check_if_location_reached(
    current_location: Location, target_location: Location, interaction_radius: float
) -> bool:
    """
    Check if the agent has reached the target location.

    Parameters
    ----------
    current_location : Location
        The current location of the agent.

    target_location : Location
        The target location to check against the agent's current location.

    interaction_radius : float
        The radius within which the agent is considered to have reached the
        target location.

    Returns
    -------
    bool
        True if the agent has reached the target location, False otherwise.

    """
    if current_location.building != target_location.building:
        return False
    if current_location.floor != target_location.floor:
        return False

    distance = current_location.distance_to(target_location)
    return distance <= interaction_radius


def propose_new_coordinates(
    coordinates: tuple[float, float],
    heading_rad: float,
    movement_speed: float,
    stochasticity: float,
    rng_generator: Generator,
) -> tuple[float, float]:
    """
    Propose a new location for agent movement.

    Parameters
    ----------
    coordinates : tuple[float, float]
        The current (x, y) coordinates of the agent.
    heading_rad : float
        The current heading of the agent in radians.
    movement_speed : float
        The speed at which the agent moves (units per time step).
    stochasticity : float
        The level of randomness to apply to the movement.
    rng_generator : Generator
        A random number generator to use for adding stochasticity to the movement.

    Returns
    -------
    tuple[float, float]
        The proposed new (x, y) coordinates for the agent after moving one step.

    """
    if stochasticity < 0:
        logger.warning(
            "Stochasticity is negative (%f). Using absolute value for calculations.",
            stochasticity,
        )
        stochasticity = abs(stochasticity)

    stochastic_heading_rad = heading_rad + rng_generator.normal(
        0, math.radians(stochasticity)
    )
    delta_x = movement_speed * math.cos(stochastic_heading_rad)
    delta_y = movement_speed * math.sin(stochastic_heading_rad)

    delta_x = (1 + rng_generator.normal(0, stochasticity)) * delta_x
    delta_y = (1 + rng_generator.normal(0, stochasticity)) * delta_y

    new_x = coordinates[0] + delta_x
    new_y = coordinates[1] + delta_y

    return new_x, new_y
