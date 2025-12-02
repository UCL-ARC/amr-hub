"""Module defining door representation for the AMR Hub ABM simulation."""

from dataclasses import dataclass, field

import shapely.geometry

from amr_hub_abm.exceptions import SimulationModeError


@dataclass
class Door:
    """Representation of a door in the AMR Hub ABM simulation."""

    door_id: int
    open: bool
    connecting_rooms: tuple[int, int]
    access_control: tuple[bool, bool]
    start: tuple[float, float] = field(default=(0.0, 0.0))
    end: tuple[float, float] = field(default=(0.0, 0.0))

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
