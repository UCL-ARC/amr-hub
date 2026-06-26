"""Collection of utility functions for the agent module."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from amr_hub_abm.space.space import get_room

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.space.content import Content

logger = logging.getLogger(__name__)


def remove_agent_occupancy(agent: Agent, current_time: int) -> None:
    """
    Remove the agent's occupancy from any content they are currently occupying.

    Parameters
    ----------
    agent : Agent
        The agent whose occupancy is to be removed.
    current_time : int
        The current time in the simulation, used for logging purposes.

    """
    room = get_room(agent.location, agent.rooms)
    if room is None:
        return
    for content in room.contents:
        if content.occupier_id == (agent.idx, agent.agent_type):
            content.occupier_id = None
            agent.stationary = False
            logger.info(
                "Agent %s released content %s (%s) in room %s at t=%d.",
                agent.idx,
                content.content_id,
                content.content_type,
                room.name,
                current_time,
            )
            return


def add_agent_occupancy(agent: Agent, content: Content, current_time: int) -> None:
    """Mark the agent as occupying the given content."""
    content.occupier_id = (agent.idx, agent.agent_type)
    agent.stationary = True

    room = get_room(agent.location, agent.rooms)

    logger.info(
        "Agent %s occupied content %s (%s) in room %s at t=%d.",
        agent.idx,
        content.content_id,
        content.content_type,
        "unknown" if room is None else room.name,
        current_time,
    )
