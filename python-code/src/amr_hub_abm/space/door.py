"""Module defining door representation for the AMR Hub ABM simulation."""

from dataclasses import dataclass, field

import shapely.geometry

from amr_hub_abm.exceptions import InvalidDoorError


@dataclass(kw_only=True, frozen=True)
class DetachedDoor:
    """Representation of a detatched door in the AMR Hub ABM simulation."""

    is_open: bool
    access_control: tuple[bool, bool]
    name: str | None = field(default=None)
    start: tuple[float, float] | None = field(default=None)
    end: tuple[float, float] | None = field(default=None)

    def _identity_key(self) -> tuple[object, ...]:
        """Key used for equality + hashing. Ignores mutable state."""
        if self.name is not None:
            return ("name", self.name)
        # at this point start/end are both not None due to validation

        if self.start is None or self.end is None:
            msg = "Cannot create identity key from door without name or coordinates."
            raise InvalidDoorError(msg)
        return ("coords", self.start, self.end)

    def __eq__(self, other: object) -> bool:
        """Define equality comparison for DetachedDoor instances."""
        if not isinstance(other, DetachedDoor):
            return NotImplemented
        return self._identity_key() == other._identity_key()

    def __hash__(self) -> int:
        """Define hash for DetachedDoor instances."""
        return hash(self._identity_key())

    def check_for_start_end_consistency(self) -> None:
        """Check that start and end points are consistent."""
        if (self.start is None) != (self.end is None):
            msg = "Both start and end points must be None or both must be defined."
            raise InvalidDoorError(msg)

    def _init_logical(self) -> None:
        if self.name is None:
            msg = "Door must have a name if start and end points are not defined."
            raise InvalidDoorError(msg)

        if (self.start is not None and self.end is not None) and self.start == self.end:
            msg = "Door start and end points cannot be the same."
            raise InvalidDoorError(msg)

    def __post_init__(self) -> None:
        """Post-initialization to validate door coordinates."""
        if self.start is None and self.end is None:
            # If both start and end are None, we are in topological mode
            # and don't need to check coordinates. We just need to ensure that the door
            # has a name for identity purposes.
            if self.name is None:
                msg = "Door must have a name if start and end points are not defined."
                raise InvalidDoorError(msg)
            return

        self.check_for_start_end_consistency()

        if self.start is None or self.end is None:
            # This should never happen due to the consistency check, but we check again
            # to address mypy's anger issues.
            msg = "Both start and end points must be defined when in spatial mode."
            raise InvalidDoorError(msg)

        if self.start > self.end:
            temp = self.start
            object.__setattr__(self, "start", self.end)
            object.__setattr__(self, "end", temp)


@dataclass(eq=False, kw_only=True, frozen=True)
class Door(DetachedDoor):
    """Representation of a door in the AMR Hub ABM simulation."""

    connecting_rooms: tuple[int, int]
    door_id: int

    def __lt__(self, other: object) -> bool:
        """Define less-than comparison for Door instances."""
        if not isinstance(other, Door):
            return NotImplemented
        return self._identity_key() < other._identity_key()

    def __post_init__(self) -> None:
        """Post-initialization to validate door coordinates and create hash."""
        super().__post_init__()

    @property
    def line(self) -> shapely.geometry.LineString:
        """Get the line representation of the door."""
        if self.start is None or self.end is None:
            msg = "Door start and end must be defined when not in topological mode."
            raise InvalidDoorError(msg)
        return shapely.geometry.LineString([self.start, self.end])
