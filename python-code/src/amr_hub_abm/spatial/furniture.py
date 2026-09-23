"""
Module defining room content types for the rooms of the AMR Hub ABM simulation.

This module defines the `Content` class, which represents the contents of rooms in the
AMR Hub ABM simulation. The `Content` class includes attributes for content type,
location, size, and occupancy status, as well as methods for calculating the polygon
representation of the content and checking if it is occupied.

"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

import shapely

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import AgentType
    from amr_hub_abm.spatial.location import Location


class ContentType(IntEnum):
    """Enumeration of possible room content types."""

    BED = 0
    WORKSTATION = 1
    CHAIR = 2


CONTENT_SIZES = {
    ContentType.BED: (0.2, 0.1),  # length x width in meters
    ContentType.WORKSTATION: (0.1, 0.05),  # length x width in meters
    ContentType.CHAIR: (0.05, 0.05),  # length x width in meters
}

CONTENT_COLORS = {
    ContentType.BED: "lightblue",
    ContentType.WORKSTATION: "lightgreen",
    ContentType.CHAIR: "lightgray",
}


@dataclass
class Content:
    """
    Representation of content within a room in the AMR Hub ABM simulation.

    Parameters
    ----------
    content_type : ContentType
        The type of content (e.g., bed, workstation, chair).
    location : Location
        The location of the content within the room.
    occupier_id : tuple[int, AgentType] | None, optional
        The ID and type of the agent currently occupying the content, if any.
        Defaults to None.
    owner_id : tuple[int, AgentType] | None, optional
        The ID and type of the agent that owns the content, if any.
        Defaults to None.
    reserver_id : tuple[int, AgentType] | None, optional
        The ID and type of the agent travelling to occupy the content, if any.
        Defaults to None.

    """

    content_id: int = field(init=False)
    content_type: ContentType
    location: Location
    color: str = field(init=False)
    size: tuple[float, float] = field(init=False)
    occupier_id: tuple[int, AgentType] | None = field(default=None)
    owner_id: tuple[int, AgentType] | None = field(default=None)
    reserver_id: tuple[int, AgentType] | None = field(default=None)

    marker_type: str = field(init=False, default="s")
    marker_size: int = field(init=False, default=100)

    def __post_init__(self) -> None:
        """Post-initialization to set content_id based on content_type and position."""
        self.content_id = hash((self.content_type, self.position))

        self.color = CONTENT_COLORS[self.content_type]
        self.size = CONTENT_SIZES[self.content_type]

    @property
    def length(self) -> float:
        """Get the length of the content based on its type."""
        return self.size[0]

    @property
    def width(self) -> float:
        """Get the width of the content based on its type."""
        return self.size[1]

    @property
    def polygon(self) -> shapely.geometry.Polygon:
        """Get the polygon representation of the content."""
        x, y = self.position
        length, width = self.size
        return shapely.geometry.box(
            x - length / 2, y - width / 2, x + length / 2, y + width / 2
        )

    @property
    def occupied(self) -> bool:
        """Check if the content is currently occupied by an agent."""
        return self.occupier_id is not None

    @property
    def reserved(self) -> bool:
        """Check if the content is reserved by an agent."""
        return self.reserver_id is not None

    @property
    def available(self) -> bool:
        """Check if the content is neither occupied nor reserved."""
        return not self.occupied and not self.reserved

    def is_available_to(self, agent_id: tuple[int, AgentType]) -> bool:
        """
        Check whether an agent may reserve this content.

        Parameters
        ----------
        agent_id : tuple[int, AgentType]
            Identity of the agent requesting the content.

        Returns
        -------
        bool
            Whether no other agent occupies or reserves the content.

        """
        valid_occupier = self.occupier_id in {None, agent_id}
        valid_reserver = self.reserver_id in {None, agent_id}
        return valid_occupier and valid_reserver

    def try_reserve(self, agent_id: tuple[int, AgentType]) -> bool:
        """
        Reserve the content if it is available to the given agent.

        Parameters
        ----------
        agent_id : tuple[int, AgentType]
            Identity of the agent requesting the reservation.

        Returns
        -------
        bool
            Whether the reservation was acquired.

        """
        if not self.is_available_to(agent_id):
            return False
        self.reserver_id = agent_id
        return True

    def release_reservation(self, agent_id: tuple[int, AgentType]) -> bool:
        """
        Release a reservation held by the given agent.

        Parameters
        ----------
        agent_id : tuple[int, AgentType]
            Identity of the agent releasing the reservation.

        Returns
        -------
        bool
            Whether a matching reservation was released.

        """
        if self.reserver_id != agent_id:
            return False
        self.reserver_id = None
        return True

    def try_occupy(self, agent_id: tuple[int, AgentType]) -> bool:
        """
        Occupy content without overwriting another agent's claim.

        Parameters
        ----------
        agent_id : tuple[int, AgentType]
            Identity of the agent occupying the content.

        Returns
        -------
        bool
            Whether occupancy was acquired.

        """
        if not self.is_available_to(agent_id):
            return False
        self.occupier_id = agent_id
        self.reserver_id = None
        return True

    def release_occupancy(self, agent_id: tuple[int, AgentType]) -> bool:
        """
        Release occupancy held by the given agent.

        Parameters
        ----------
        agent_id : tuple[int, AgentType]
            Identity of the agent releasing occupancy.

        Returns
        -------
        bool
            Whether matching occupancy was released.

        """
        if self.occupier_id != agent_id:
            return False
        self.occupier_id = None
        return True

    @property
    def owned(self) -> bool:
        """Check if the content is currently owned by an agent."""
        return self.owner_id is not None

    @property
    def position(self) -> tuple[float, float]:
        """Get the (x, y) position of the content."""
        return (self.location.x, self.location.y)
