"""Module containing building representation for the AMR Hub ABM simulation."""

from dataclasses import dataclass

from matplotlib.axes import Axes

from amr_hub_abm.space.floor import Floor


@dataclass
class Building:
    """Representation of a building in the AMR Hub ABM simulation."""

    name: str
    floors: list[Floor]

    def plot_building(self, axes: list[Axes]) -> None:
        """Plot the building layout."""
        for floor, ax in zip(self.floors, axes, strict=True):
            floor.plot(ax=ax)
