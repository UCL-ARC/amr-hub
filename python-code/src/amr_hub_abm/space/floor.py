"""Module for Floor class."""

from collections.abc import Sequence
from dataclasses import dataclass

from amr_hub_abm.space.room import Room


@dataclass
class Floor:
    """Representation of a floor in a building."""

    floor_number: int
    rooms: Sequence[Room]
