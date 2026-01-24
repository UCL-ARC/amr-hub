"""Module defining door representation for the AMR Hub ABM simulation."""

import hashlib
from dataclasses import dataclass, field

import shapely.geometry

from amr_hub_abm.exceptions import InvalidDoorError


@dataclass
class Door:
    """Representation of a door in the AMR Hub ABM simulation."""

    open: bool
    connecting_rooms: tuple[int, int]
    access_control: tuple[bool, bool]
    name: str | None = field(default=None)
    start: tuple[float, float] | None = field(default=None)
    end: tuple[float, float] | None = field(default=None)
    door_hash: str = field(init=False)
    door_id: int = field(init=False, repr=False)

    def __eq__(self, value: object) -> bool:
        """Check equality of two Door instances based on their attributes."""
        if not isinstance(value, Door):
            return False

        if self.name is not None and value.name is not None:
            return self.name == value.name

        return (self.start, self.end, self.connecting_rooms) == (
            value.start,
            value.end,
            value.connecting_rooms,
        )

    def __lt__(self, other: object) -> bool:
        """Define less-than comparison for sorting Door instances."""
        if not isinstance(other, Door):
            return NotImplemented

        if self.name is not None and other.name is not None:
            return self.name < other.name

        return (self.start, self.end, self.connecting_rooms) < (
            other.start,
            other.end,
            other.connecting_rooms,
        )

    def __post_init__(self) -> None:
        """Post-initialization to validate door coordinates."""
        if (self.start is None or self.end is None) and (self.start != self.end):
            msg = "Both start and end points must be None or both must be defined."
            raise InvalidDoorError(msg)

        if (self.start is None or self.end is None) and (self.name is None):
            msg = "Door must have a name if start and end points are not defined."
            raise InvalidDoorError(msg)

        if self.start is None or self.end is None:
            self.door_hash = self.create_name_hash()
            return

        if self.start == self.end:
            msg = "Door start and end points cannot be the same."
            raise InvalidDoorError(msg)

        if self.start > self.end:
            self.start, self.end = self.end, self.start

        self.door_hash = self.create_coordinate_hash()

    def __hash__(self) -> int:
        """Generate a hash for the door based on its unique hash string."""
        return hash(self.door_hash)

    def create_name_hash(self) -> str:
        """Generate a hash for the door based on its name."""
        if self.name is None:
            msg = "Door name must be defined to create name-based hash."
            raise InvalidDoorError(msg)
        hash_input = f"{self.name}-{self.connecting_rooms}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def create_coordinate_hash(self) -> str:
        """Generate a hash for the door based on its unique attributes."""
        hash_input = f"{self.start}-{self.end}-{self.connecting_rooms}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

    @property
    def line(self) -> shapely.geometry.LineString:
        """Get the line representation of the door."""
        if self.start is None or self.end is None:
            msg = "Door start and end must be defined when not in topological mode."
            raise InvalidDoorError(msg)
        return shapely.geometry.LineString([self.start, self.end])
