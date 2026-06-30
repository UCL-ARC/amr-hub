"""Collection of utility functions for the agent module."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.space.content import Content
    from amr_hub_abm.space.space import SpatialQuery

logger = logging.getLogger(__name__)


def remove_agent_occupancy(
    agent: Agent, current_time: int, engine: SpatialQuery
) -> None:
    """
    Remove the agent's occupancy from any content they are currently occupying.

    Parameters
    agent : Agent
        The agent whose occupancy is to be removed.
    current_time : int
        The current time in the simulation, used for logging purposes.
    engine : SpatialQuery
        The engine instance used to resolve geometry queries.

    """
    room = engine.get_room(agent)
    if room is None:
        return
    for content in room.contents:
        if content.occupier_id == (agent.idx, agent.agent_type):
            content.occupier_id = None
            agent.stationary = False
            logger.info(
                """
                Agent id %s removed occupancy from content id %s of type %s
                in room %s at time %d.
                """,
                agent.idx,
                content.content_id,
                content.content_type,
                room.name,
                current_time,
            )
            return


def add_agent_occupancy(
    agent: Agent, content: Content, current_time: int, engine: SpatialQuery
) -> None:
    """
    Add the agent's occupancy to the specified content.

    Parameters
    agent : Agent
        The agent whose occupancy is to be added.
    content : Content
        The content to which the agent will occupy.
    current_time : int
        The current time in the simulation, used for logging purposes.
    engine : SpatialQuery
        The engine instance used to resolve geometry queries.

    """
    content.occupier_id = (agent.idx, agent.agent_type)
    agent.stationary = True

    room = engine.get_room(agent)
    room_name = "unknown" if room is None else room.name

    logger.info(
        """
        Agent id %s added occupancy to content id %s of type %s
        in room %s at time %d.
        """,
        agent.idx,
        content.content_id,
        content.content_type,
        room_name,
        current_time,
    )
