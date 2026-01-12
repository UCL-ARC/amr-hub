"""Module defining door representation for the AMR Hub ABM simulation."""

import hashlib
from dataclasses import dataclass, field

import shapely.geometry

from amr_hub_abm.exceptions import InvalidDoorError, SimulationModeError


@dataclass
class Door:
    """Representation of a door in the AMR Hub ABM simulation."""

    door_id: int
    open: bool
    connecting_rooms: tuple[int, int]
    access_control: tuple[bool, bool]
    start: tuple[float, float] = field(default=(0.0, 0.0))
    end: tuple[float, float] = field(default=(0.0, 0.0))
    door_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Post-initialization to validate door coordinates."""
        if self.start == self.end:
            msg = "Door start and end points cannot be the same."
            raise InvalidDoorError(msg)

        if self.start > self.end:
            self.start, self.end = self.end, self.start

        self.door_hash = self.create_coordinate_hash()

    def __hash__(self) -> int:
        """Generate a hash for the door based on its unique hash string."""
        return hash(self.door_hash)

    def __eq__(self, other: object) -> bool:
        """Check equality of two Door instances based on their attributes."""
        if not isinstance(other, Door):
            return NotImplemented
        return self.door_hash == other.door_hash

    def create_coordinate_hash(self) -> str:
        """Generate a hash for the door based on its unique attributes."""
        hash_input = f"{self.start}-{self.end}-{self.connecting_rooms}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

    @property
    def line(self) -> shapely.geometry.LineString:
        """Get the line representation of the door."""
        if self.start == self.end == (0.0, 0.0):
            msg = """
            Dummy start and end points for door line.
            Probably simulation in topological mode.
            """
            raise SimulationModeError(msg)
        return shapely.geometry.LineString([self.start, self.end])
