"""Module containing space related functions and of agent."""

import logging

from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room

logger = logging.getLogger(__name__)


def get_room(
    location: Location,
    rooms: list[Room],
) -> Room | None:
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

    return None

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
