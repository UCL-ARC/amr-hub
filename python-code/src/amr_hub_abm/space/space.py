"""Module containing space related functions and of agent."""

import logging
from dataclasses import dataclass

from amr_hub_abm.space.building import Building
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room

logger = logging.getLogger(__name__)


@dataclass
class Space:
    """
    The Space class represents the physical environment in which agents operate.

    It containsa list of buildings, each of which contains floors and rooms.

    Arguments:
    ---------
    space : list[Building]
        A list of Building objects representing the buildings in the environment.

    """

    space: list[Building]

    def get_room(
        self,
        location: Location,
    ) -> Room | None:
        """
        Identify the room in which the given co-ordinates are located.

        Parameters
        ----------
        location : Location
            The location for which the room is to be identified.

        Returns
        -------
        Room | None
            The room in which the agent is located, or None if the agent is not located
            in any room.

        """
        for building in self.space:
            if building.name != location.building:
                continue
            for floor in building.floors:
                if floor.floor_number != location.floor:
                    continue
                room = floor.find_room_by_location((location.x, location.y))
                if room:
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
