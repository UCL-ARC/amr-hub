"""Plotting utilities for the AMR Hub ABM space module."""

from matplotlib.axes import Axes

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.spatial.room import Room


def plot_room(
    room: Room,
    ax: Axes,
    *,
    door_color: str = "brown",
    door_width: float = 2.0,
) -> None:
    """
    Plot a room on the given axes.

    Parameters
    ----------
    room : Room
        The room to plot.
    ax : Axes
        The axes on which to plot the room.
    door_color : str, optional
        Colour used to plot doors. Defaults to ``"brown"``.
    door_width : float, optional
        Line width used to plot doors. Defaults to 2.0.

    """
    if not room.walls:
        msg = "Cannot plot room without walls."
        raise SimulationModeError(msg)

    for wall in room.walls:
        wall.plot(ax, color="black")  # type: ignore  # noqa: PGH003

    for door in room.doors:
        x, y = door.line.xy
        ax.plot(
            x,
            y,
            color=door_color,
            linewidth=door_width,
        )

    for content in room.contents:
        ax.scatter(
            content.position[0],
            content.position[1],
            marker=content.marker_type,
            color=content.color,
            s=content.marker_size,
            label=f"{content.content_type.name} ({content.content_id})",
        )
        ax.text(
            content.position[0] + 0.05,
            content.position[1] - 0.15,
            content.content_type.name.lower(),  # "bed", "chair", "workstation"
            fontsize=6,
            ha="left",
            va="top",
            color="gray",
            alpha=0.7,
        )
