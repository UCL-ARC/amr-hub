"""Module defining door representation for the AMR Hub ABM simulation."""

import hashlib
from dataclasses import dataclass, field

import shapely.geometry

from amr_hub_abm.exceptions import InvalidDoorError


@dataclass
class Door:
    """Representation of a door in the AMR Hub ABM simulation."""

    door_id: int
    open: bool
    connecting_rooms: tuple[int, int]
    access_control: tuple[bool, bool]
    name: str | None = field(default=None)
    start: tuple[float, float] | None = field(default=None)
    end: tuple[float, float] | None = field(default=None)
    door_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Post-initialization to validate door coordinates."""
        no_coords = self.start is None and self.end is None
        if no_coords:
            self._init_logical()
            return

        missing_a_coord = self.start is None or self.end is None

        if missing_a_coord:
            msg = "Both start and end points must be None or both must be defined."
            raise InvalidDoorError(msg)

        self._init_spatial()

    def _init_logical(self) -> None:
        if self.name is None:
            msg = "Door must have a name if start and end points are not defined."
            raise InvalidDoorError(msg)

        self.door_hash = self.create_name_hash()

    def _init_spatial(self) -> None:
        if self.start is None or self.end is None:
            # This code should be unreachable but acts as a guard for mypy
            # It guarantees to mypy that when we do start-end comparisons they
            # are of appropriate types
            msg = "Unreachable"
            raise InvalidDoorError(msg)

        start: tuple[float, float] = self.start
        end: tuple[float, float] = self.end

        if start == end:
            msg = "Door start and end points cannot be the same."
            raise InvalidDoorError(msg)

        if start > end:
            self.start, self.end = end, start

        self.door_hash = self.create_coordinate_hash()

    def __hash__(self) -> int:
        """Generate a hash for the door based on its unique hash string."""
        return hash(self.door_hash)

    def __eq__(self, other: object) -> bool:
        """Check equality of two Door instances based on their attributes."""
        if not isinstance(other, Door):
            return NotImplemented
        return self.door_hash == other.door_hash

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
