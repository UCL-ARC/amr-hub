"""Module defining room content types for the rooms of the AMR Hub ABM simulation."""

from dataclasses import dataclass, field
from enum import IntEnum

import shapely


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
    position: tuple[float, float]
    color: str = field(init=False)
    size: tuple[float, float] = field(init=False)

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
