"""Module containing building representation for the AMR Hub ABM simulation."""

from dataclasses import dataclass

from amr_hub_abm.space.floor import Floor


@dataclass
class Building:
    """Representation of a building in the AMR Hub ABM simulation."""

    name: str
    floors: list[Floor]
