"""Module defining wall representation for the AMR Hub ABM simulation."""

from dataclasses import dataclass

import shapely.geometry
from matplotlib.axes import Axes


@dataclass
class Wall:
    """Representation of a wall in the AMR Hub ABM simulation."""

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
        """Plot the wall on a given matplotlib axis."""
        x, y = self.polygon.exterior.xy
        ax.fill(x, y, **kwargs)  # pyright: ignore[reportArgumentType]
