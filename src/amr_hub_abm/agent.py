"""Module to represent an agent in the AMR Hub ABM simulation."""

from dataclasses import dataclass
from enum import Enum
from logging import getLogger

from amr_hub_abm.space import Location

logger = getLogger(__name__)


class AgentType(Enum):
    """Enumeration of possible agent types."""

    GENERIC = "generic"
    PATIENT = "patient"
    HEALTHCARE_WORKER = "healthcare_worker"


class InfectionStatus(Enum):
    """Enumeration of possible infection statuses."""

    SUSCEPTIBLE = "susceptible"
    EXPOSED = "exposed"
    INFECTED = "infected"
    RECOVERED = "recovered"


@dataclass
class Agent:
    """Representation of an agent in the AMR Hub ABM simulation."""

    idx: int
    agent_type: AgentType
    infection_status: InfectionStatus
    location: Location
    heading: float

    def __post_init__(self) -> None:
        """Post-initialization to log agent creation."""
        self.heading = self.heading % 360

        logger.debug(
            "Created Agent id %s of type %s at location %s with heading %s",
            self.idx,
            self.agent_type,
            self.location,
            self.heading,
        )
