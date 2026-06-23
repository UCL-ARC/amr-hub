"""
Module containing building representation for the AMR Hub ABM simulation.

This module defines the `Building` class, which represents a building in the AMR Hub ABM
simulation. The `Building` class contains a list of `Floor` objects and provides methods
for plotting the building layout and sorting/numbering buildings by name.

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.space.floor import Floor


@dataclass
class Building:
    """
    Representation of a building in the AMR Hub ABM simulation.

    Parameters
    ----------
    name : str
        The name of the building.
    floors : list[Floor]
        The list of floors in the building.

    """

    idx: int = field(init=False, repr=False)
    name: str
    floors: list[Floor]

    def plot_building(
        self,
        axes: list[Axes],
        agents: list[Agent] | None = None,
        *,
        trajectory: bool = False,
    ) -> None:
        """
        Plot the building layout.

        Parameters
        ----------
        axes : list[Axes]
            The list of matplotlib axes to plot on.
        agents : list[Agent] | None, optional
            The list of agents to plot. Defaults to None.
        trajectory : bool, optional
            Whether to plot the trajectory of the agents. Defaults to False.

        """
        for floor, ax in zip(self.floors, axes, strict=True):
            floor.plot(ax=ax, agents=agents, trajectory=trajectory)

    @staticmethod
    def sort_and_number_buildings(buildings: list[Building]) -> list[Building]:
        """
        Sort and number buildings by name.

        Parameters
        ----------
        buildings : list[Building]
            The list of buildings to sort and number.

        Returns
        -------
        list[Building]
            The sorted and numbered list of buildings.

        """
        sorted_buildings = sorted(buildings, key=lambda b: b.name)
        for i, building in enumerate(sorted_buildings):
            building.idx = i
        return sorted_buildings
