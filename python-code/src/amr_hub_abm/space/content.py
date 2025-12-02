"""Module defining room content types for the rooms of the AMR Hub ABM simulation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class ContentType(Enum):
    """Enumeration of possible room content types."""

    BED = "bed"
    WORKSTATION = "workstation"


@dataclass
class Content(ABC):
    """Enumeration of possible room contents."""

    content_type: ContentType

    @abstractmethod
    def get_id(self) -> int:
        """Get the unique identifier of the content."""


@dataclass
class Bed(Content):
    """Representation of a bed in the AMR Hub ABM simulation."""

    bed_id: int
    content_type: ContentType = field(default=ContentType.BED, init=False)

    def get_id(self) -> int:
        """Get the unique identifier of the bed."""
        return self.bed_id


@dataclass
class Workstation(Content):
    """Representation of a workstation in the AMR Hub ABM simulation."""

    workstation_id: int
    content_type: ContentType = field(default=ContentType.WORKSTATION, init=False)

    def get_id(self) -> int:
        """Get the unique identifier of the workstation."""
        return self.workstation_id
