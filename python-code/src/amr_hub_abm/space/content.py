"""Module defining room content types for the rooms of the AMR Hub ABM simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

import shapely

if TYPE_CHECKING:
    from amr_hub_abm.agent import AgentType
    from amr_hub_abm.space.location import Location


class ContentType(IntEnum):
    """Enumeration of possible room content types."""

    BED = 0
    WORKSTATION = 1
    CHAIR = 2


CONTENT_SIZES = {
    ContentType.BED: (0.2, 0.1),  # length x width in meters
    ContentType.WORKSTATION: (0.1, 0.05),  # length x width in meters
    ContentType.CHAIR: (0.05, 0.05),  # length x width in meters
}

CONTENT_COLORS = {
    ContentType.BED: "lightblue",
    ContentType.WORKSTATION: "lightgreen",
    ContentType.CHAIR: "lightgray",
}


@dataclass
class Content:
    """Enumeration of possible room contents."""

    content_id: int = field(init=False)
    content_type: ContentType
    location: Location
    color: str = field(init=False)
    size: tuple[float, float] = field(init=False)
    occupier_id: tuple[int, AgentType] | None = field(default=None)

    marker_type: str = field(init=False, default="s")
    marker_size: int = field(init=False, default=100)

    def __post_init__(self) -> None:
        """Post-initialization to set content_id based on content_type and position."""
        self.content_id = hash((self.content_type, self.position))

        self.color = CONTENT_COLORS[self.content_type]
        self.size = CONTENT_SIZES[self.content_type]

    @property
    def length(self) -> float:
        """Get the length of the content based on its type."""
        return self.size[0]

    @property
    def width(self) -> float:
        """Get the width of the content based on its type."""
        return self.size[1]

    @property
    def polygon(self) -> shapely.geometry.Polygon:
        """Get the polygon representation of the content."""
        x, y = self.position
        length, width = self.size
        return shapely.geometry.box(
            x - length / 2, y - width / 2, x + length / 2, y + width / 2
        )

    @property
    def occupied(self) -> bool:
        """Check if the content is currently occupied by an agent."""
        return self.occupier_id is not None

    @property
    def position(self) -> tuple[float, float]:
        """Get the (x, y) position of the content."""
        return (self.location.x, self.location.y)
