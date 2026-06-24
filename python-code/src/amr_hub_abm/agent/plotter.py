"""Module containing plotting functions for agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from amr_hub_abm.agent.enums import (
    INFECTION_RING_COLOUR,
    ROLE_COLOUR_MAP,
    InfectionStatus,
)
from amr_hub_abm.exceptions import InvalidRoomError
from amr_hub_abm.task.task import TaskAttendPatient, TaskProgress

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.space.room import Room


def plot_agent(agent: Agent, ax: Axes, *, show_tags: bool = True) -> None:
    """
    Plot the agent on the given axes.

    Parameters
    ----------
    ax : Axes
        The axes on which to plot the agent.
    show_tags : bool, optional
        Whether to show tags with the agent's type and index.

    """
    ring_colour = INFECTION_RING_COLOUR[agent.infection_status]
    if ring_colour is not None:
        ax.plot(
            agent.location.x,
            agent.location.y,
            marker="o",
            markersize=12,  # bigger than the inner dot
            markerfacecolor="none",  # hollow ring
            markeredgecolor=ring_colour,
            markeredgewidth=2,
            zorder=2,
        )

    ax.plot(
        agent.location.x,
        agent.location.y,
        marker="o",
        markersize=5,
        color=ROLE_COLOUR_MAP[agent.agent_type],
    )

    if not show_tags:
        return

    # Build the multi-line label
    role = agent.agent_type.name.replace("_", " ").title()
    lines = [f"{role} {agent.idx}"]

    if agent.infection_status != InfectionStatus.SUSCEPTIBLE:
        lines.append(f"({agent.infection_status.name.lower()})")

    # Find what to display: in-progress task takes priority, else next NOT_STARTED
    in_progress = next(
        (t for t in agent.tasks if t.progress == TaskProgress.IN_PROGRESS),
        None,
    )
    moving = next(
        (t for t in agent.tasks if t.progress == TaskProgress.MOVING_TO_LOCATION),
        None,
    )
    upcoming = [t for t in agent.tasks if t.progress == TaskProgress.NOT_STARTED]
    next_upcoming = (
        min(upcoming, key=lambda t: (t.time_due, t.priority.value))
        if upcoming
        else None
    )

    display_task = in_progress or moving or next_upcoming
    if display_task is not None:
        task_name = display_task.task_type.name.lower()
        if isinstance(display_task, TaskAttendPatient):
            task_name += f" → patient {display_task.patient.idx}"

        if display_task.progress == TaskProgress.IN_PROGRESS:
            prefix = "doing"
        elif display_task.progress == TaskProgress.MOVING_TO_LOCATION:
            prefix = "moving to"
        else:
            prefix = "next"
        lines.append(f"[{prefix}: {task_name}]")

    ax.text(
        agent.location.x + 0.1,
        agent.location.y + 0.05,
        "\n".join(lines),
        fontsize=7,
        ha="left",
        va="bottom",
    )


def plot_trajectory(agent: Agent, ax: Axes, current_time: int | None = None) -> None:
    """
    Plot the agent's trajectory on the given axes.

    Parameters
    ----------
    ax : Axes
        The axes on which to plot the agent's trajectory.

    """
    if agent.trajectory_length == 0:
        msg = "Cannot plot trajectory for agent with trajectory_length of 0."
        raise ValueError(msg)

    end = current_time if current_time is not None else agent.trajectory_length
    if end <= 0:
        return

    ax.plot(
        agent.trajectory.position[:, 0],
        agent.trajectory.position[:, 1],
        linestyle="-",
        linewidth=1.5,
        color=ROLE_COLOUR_MAP[agent.agent_type],
        alpha=0.7,
    )


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
