"""Module defining room content types for the rooms of the AMR Hub ABM simulation."""

from dataclasses import dataclass
from enum import IntEnum


class ContentType(IntEnum):
    """Enumeration of possible room content types."""

    BED = 0
    WORKSTATION = 1


@dataclass
class Content:
    """Enumeration of possible room contents."""

    content_id: int
    content_type: ContentType
