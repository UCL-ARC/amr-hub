"""Module containing building representation for the AMR Hub ABM simulation."""

from dataclasses import dataclass


@dataclass
class Building:
    """Representation of a building in the AMR Hub ABM simulation."""

    name: str
