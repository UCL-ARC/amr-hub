"""Module for plotting agents in rooms."""

from __future__ import annotations

from typing import TYPE_CHECKING

from amr_hub_abm.agent.plotter import plot_agent, plot_trajectory
from amr_hub_abm.exceptions import InvalidRoomError

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.space.room import Room


def plot_agents_in_room(
    room: Room,
    ax: Axes,
    agents: list[Agent],
    *,
    trajectory: bool = False,
) -> None:
    """Plot agents located inside a room."""
    if not room.walls:
        msg = "Cannot plot room without walls. Please provide wall definitions."
        raise InvalidRoomError(msg)

    for agent in agents:
        if (
            agent.location.building == room.building
            and agent.location.floor == room.floor
            and room.contains_point((agent.location.x, agent.location.y))
        ):
            plot_agent(agent, ax)

            if trajectory and agent.agent_type.value == 2:
                plot_trajectory(agent, ax)
