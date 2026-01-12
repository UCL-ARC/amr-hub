"""Module defining room content types for the rooms of the AMR Hub ABM simulation."""

from dataclasses import dataclass
from enum import Enum


class ContentType(Enum):
    """Enumeration of possible room content types."""

    BED = "bed"
    WORKSTATION = "workstation"


@dataclass
class Content:
    """Enumeration of possible room contents."""

    content_id: int
    content_type: ContentType
