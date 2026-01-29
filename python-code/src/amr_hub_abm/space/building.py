"""Module containing building representation for the AMR Hub ABM simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from amr_hub_abm.agent import Agent
    from amr_hub_abm.space.floor import Floor


@dataclass
class Building:
    """Representation of a building in the AMR Hub ABM simulation."""

    name: str
    floors: list[Floor]

    def plot_building(
        self, axes: list[Axes], agents: list[Agent] | None = None
    ) -> None:
        """Plot the building layout."""
        for floor, ax in zip(self.floors, axes, strict=True):
            floor.plot(ax=ax, agents=agents)
