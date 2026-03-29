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
    polygon: list[tuple[float, float]] = field(init=False)
    size: float = field(init=False)
