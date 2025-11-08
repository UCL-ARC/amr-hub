"""Module to represent an agent in the AMR Hub ABM simulation."""

from dataclasses import dataclass
from enum import Enum


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
