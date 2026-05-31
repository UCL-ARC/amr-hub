"""
Module defining door representation for the AMR Hub ABM simulation.

This module defines the `Door` and `DetachedDoor` classes, which represent doors in the
AMR Hub ABM simulation. The `Door` class includes attributes for the rooms it connects
and a unique ID, while the `DetachedDoor` class is a more flexible representation that
can be used for doors that are not yet fully defined. Both classes include validation to
ensure that door coordinates are consistent and that doors have a unique identity based
on either their name or their coordinates.

"""

from dataclasses import dataclass, field

import shapely.geometry

from amr_hub_abm.exceptions import InvalidDoorError


# --8<--- [start:DetachedDoor]
@dataclass(kw_only=True, frozen=True)
class DetachedDoor:
    """
    Representation of a detached door in the AMR Hub ABM simulation.

    Created to allow for more flexible door representations that can be used for doors
    that are newly read in from input files but whose connecting rooms have not yet been
    identified. Serves as a base class for the `Door` class, which includes additional
    attributes for connecting rooms and a unique ID.

    Parameters
    ----------
    is_open : bool
        Whether the door is currently open.
    access_control : tuple[bool, bool]
        A tuple indicating whether the door allows access from each side.
    name : str | None, optional
        The name of the door, if applicable.
    start : tuple[float, float] | None, optional
        The starting point of the door in the spatial representation.
    end : tuple[float, float] | None, optional
        The ending point of the door in the spatial representation.

    """

    is_open: bool
    access_control: tuple[bool, bool]
    name: str | None = field(default=None)
    start: tuple[float, float] | None = field(default=None)
    end: tuple[float, float] | None = field(default=None)

    # --8<--- [end:DetachedDoor]

    def _identity_key(self) -> tuple[object, ...]:
        """
        Key used for equality and hashing.

        If name is defined, use that as the identity key. Otherwise, use the
        coordinates.

        Returns
        -------
        tuple[object, ...]
            The identity key for the door, based on either its name or its coordinates.

        Raises
        ------
        InvalidDoorError
            If the door has neither a name nor defined coordinates.

        """
        if self.name is not None:
            return ("name", self.name)
        # at this point start/end are both not None due to validation

        if self.start is None or self.end is None:
            msg = "Cannot create identity key from door without name or coordinates."
            raise InvalidDoorError(msg)
        return ("coords", self.start, self.end)

    def __eq__(self, other: object) -> bool:
        """
        Define equality comparison for DetachedDoor instances.

        Two DetachedDoor instances are considered equal if they have the same name (if
        defined) or the same coordinates (if name is not defined).

        Parameters
        ----------
        other : object
            The other object to compare against.

        Returns
        -------
        bool
            True if the two DetachedDoor instances are considered equal,
            False otherwise.

        Raises
        ------
        NotImplementedError
            If the other object is not an instance of DetachedDoor.

        """
        if not isinstance(other, DetachedDoor):
            msg = f"Cannot compare DetachedDoor with object of type {type(other)}."
            raise NotImplementedError(msg)
        return self._identity_key() == other._identity_key()

    def __hash__(self) -> int:
        """Define hash for DetachedDoor instances."""
        return hash(self._identity_key())

    def check_for_start_end_consistency(self) -> None:
        """
        Check that start and end points are consistent.

        Raises
        ------
        InvalidDoorError
            If one of start or end is defined but not the other, or if start and end
            are the same point.

        """
        if (self.start is None) != (self.end is None):
            msg = "Both start and end points must be None or both must be defined."
            raise InvalidDoorError(msg)

        if (self.start is not None and self.end is not None) and self.start == self.end:
            msg = "Door start and end points cannot be the same."
            raise InvalidDoorError(msg)

    def __post_init__(self) -> None:
        """
        Post-initialization to validate door coordinates.

        Raises
        ------
        InvalidDoorError
            If the door has inconsistent start and end points, or if it has no name and
            no coordinates.

        """
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


# --8<--- [start:Door]


@dataclass(eq=False, kw_only=True, frozen=True)
class Door(DetachedDoor):
    """
    Representation of a door in the AMR Hub ABM simulation.

    Inherits from `DetachedDoor` and adds attributes for the rooms it connects and a
    unique ID. The `Door` class includes validation to ensure that door coordinates are
    consistent and that the door has a unique identity based on either its name or its
    coordinates.

    Parameters
    ----------
    connecting_rooms : tuple[int, int]
        The IDs of the two rooms that the door connects.
    door_id : int
        A unique identifier for the door.

    """

    connecting_rooms: tuple[int, int]
    door_id: int

    # --8<--- [end:Door]

    def __lt__(self, other: object) -> bool:
        """
        Define less-than comparison for Door instances.

        This allows for sorting of Door instances based on their identity key, which is
        determined by either their name or their coordinates.

        Parameters
        ----------
        other : object
            The other object to compare against.

        Returns
        -------
        bool
            True if this Door instance is considered less than the other, False
            otherwise.

        Raises
        ------
        NotImplementedError
            If the other object is not an instance of Door.

        """
        if not isinstance(other, Door):
            return NotImplemented
        return self._identity_key() < other._identity_key()

    def __post_init__(self) -> None:
        """Post-initialization to validate door coordinates and create hash."""
        super().__post_init__()

    @property
    def line(self) -> shapely.geometry.LineString:
        """
        Get the line representation of the door.

        Returns
        -------
        shapely.geometry.LineString
            The line representation of the door based on its start and end coordinates.

        Raises
        ------
        InvalidDoorError
            If the door does not have defined start and end coordinates.

        """
        if self.start is None or self.end is None:
            msg = "Door start and end must be defined when not in topological mode."
            raise InvalidDoorError(msg)
        return shapely.geometry.LineString([self.start, self.end])
