"""Module defining room content types for the rooms of the AMR Hub ABM simulation."""

from dataclasses import dataclass, field
from enum import IntEnum


class ContentType(IntEnum):
    """Enumeration of possible room content types."""

    BED = 0
    WORKSTATION = 1
    CHAIR = 2


@dataclass
class Content:
    """Enumeration of possible room contents."""

    content_id: int = field(init=False)
    content_type: ContentType
    position: tuple[float, float]

    def __post_init__(self) -> None:
        """Post-initialization to set content_id based on content_type and position."""
        self.content_id = hash((self.content_type, self.position))
