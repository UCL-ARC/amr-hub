"""Module defining wall representation for the AMR Hub ABM simulation."""

from dataclasses import dataclass

import shapely.geometry
from matplotlib.axes import Axes


@dataclass
class Wall:
    """
    Representation of a wall in the AMR Hub ABM simulation.

    Parameters
    ----------
    start : tuple[float, float]
        The starting coordinates of the wall as a tuple (x, y).
    end : tuple[float, float]
        The ending coordinates of the wall as a tuple (x, y).
    thickness : float, optional
        The thickness of the wall. Defaults to 0.2 units.

    """

    start: tuple[float, float]
    end: tuple[float, float]
    thickness: float = 0.2

    @property
    def line(self) -> shapely.geometry.LineString:
        """Get the line representation of the wall."""
        return shapely.geometry.LineString([self.start, self.end])

    @property
    def polygon(self) -> shapely.geometry.Polygon:
        """Get the polygon representation of the wall based on its thickness."""
        line = self.line
        return line.buffer(self.thickness / 2, cap_style="square")

    def plot(self, ax: Axes, **kwargs: dict) -> None:
        """
        Plot the wall on a given matplotlib axis.

        Parameters
        ----------
        ax : matplotlib.axes.Axes
            The axis on which to plot the wall.
        **kwargs : dict
            Additional keyword arguments to pass to the fill
            method for styling the wall (e.g., color, alpha).

        """
        x, y = self.polygon.exterior.xy
        ax.fill(x, y, **kwargs)  # pyright: ignore[reportArgumentType]
