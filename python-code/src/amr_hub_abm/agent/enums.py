"""Module defining enumerations for agent types and infection statuses."""

from enum import IntEnum


class AgentType(IntEnum):
    """Enumeration of possible agent types."""

    GENERIC = 0
    PATIENT = 1
    HEALTHCARE_WORKER = 2


class InfectionStatus(IntEnum):
    """Enumeration of possible infection statuses."""

    SUSCEPTIBLE = 0
    EXPOSED = 1
    INFECTED = 2
    RECOVERED = 3


ROLE_COLOUR_MAP = {
    AgentType.GENERIC: "blue",
    AgentType.PATIENT: "red",
    AgentType.HEALTHCARE_WORKER: "green",
}

INFECTION_RING_COLOUR = {
    InfectionStatus.SUSCEPTIBLE: None,  # no ring
    InfectionStatus.EXPOSED: "gold",
    InfectionStatus.INFECTED: "darkred",
    InfectionStatus.RECOVERED: "blue",
}
