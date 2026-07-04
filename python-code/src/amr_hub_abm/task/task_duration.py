"""Module defining task duration configurations for the AMR Hub ABM simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amr_hub_abm.exceptions import InvalidDefinitionError

#: Keys that must be present in the simulation config file for task durations.
REQUIRED_TASK_DURATION_KEYS: tuple[str, ...] = (
    "time_needed_attend_patient",
    "time_needed_door_access",
    "time_needed_workstation",
    "time_needed_occupy_content",
)

ALLOWED_EVENT_TYPE_STRINGS: tuple[str, ...] = (
    "attend_patient",
    "door_access",
    "workstation",
    "occupy_content",
)


@dataclass(frozen=True)
class TaskDurationConfig:
    """
    Task duration parameters read from the simulation configuration file.

    Parameters
    ----------
    time_needed_attend_patient : int
        Timesteps needed for a healthcare worker to attend to a patient.
    time_needed_door_access : int
        Timesteps needed for a healthcare worker to access a door (e.g., open/close).
    time_needed_workstation : int
        Timesteps needed for a healthcare worker to use a workstation.
    time_needed_occupy_content : int
        Timesteps needed for a healthcare worker to occupy content
        (e.g. a bed, a chair, etc.).

    """

    time_needed_attend_patient: int
    time_needed_door_access: int
    time_needed_workstation: int
    time_needed_occupy_content: int

    @classmethod
    def from_config(cls, config_data: dict[str, Any]) -> TaskDurationConfig:
        """
        Build a ``TaskDurationConfig`` from parsed YAML configuration data.

        There are deliberately no fallback defaults here: task durations must
        be defined explicitly in the simulation config file.

        Parameters
        ----------
        config_data : dict[str, Any]
            The parsed simulation configuration.

        Returns
        -------
        TaskDurationConfig
            The task duration parameters read from the config.

        """
        missing_keys = [
            key for key in REQUIRED_TASK_DURATION_KEYS if key not in config_data
        ]
        if missing_keys:
            msg = "Missing required task duration keys in simulation config: "
            msg += f"{missing_keys}"
            raise InvalidDefinitionError(msg)

        return cls(
            time_needed_attend_patient=config_data["time_needed_attend_patient"],
            time_needed_door_access=config_data["time_needed_door_access"],
            time_needed_workstation=config_data["time_needed_workstation"],
            time_needed_occupy_content=config_data["time_needed_occupy_content"],
        )

    @property
    def task_duration_mapping(self) -> dict[str, int]:
        """
        Get a mapping of event type strings to their corresponding task durations.

        Returns
        -------
        dict[str, int]
            A dictionary mapping event type strings to task durations in timesteps.

        """
        return {
            "attend_patient": self.time_needed_attend_patient,
            "door_access": self.time_needed_door_access,
            "workstation": self.time_needed_workstation,
            "occupy_content": self.time_needed_occupy_content,
        }
