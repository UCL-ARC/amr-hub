"""Module defining all custom exceptions for the AMR Hub ABM simulation."""


class SimulationModeError(Exception):
    """Exception raised when an operation is invalid for the current simulation mode."""

    def __init__(self, message: str) -> None:
        """Initialize the SimulationModeError."""
        super().__init__(f"Simulation mode error: {message}.")


class InvalidDistanceError(Exception):
    """Exception raised when an invalid distance calculation is attempted."""

    def __init__(self, locations: tuple, building: bool) -> None:  # noqa: FBT001
        """Initialize the InvalidDistanceError."""
        initial_string = "Invalid distance calculation between"

        if building:
            super().__init__(
                f"{initial_string} buildings: {locations[0]} and {locations[1]}."
            )
        else:
            super().__init__(
                f"{initial_string} floors: {locations[0]} and {locations[1]}."
            )


class NegativeTimeError(Exception):
    """Exception raised when a negative time value is encountered."""

    def __init__(self, time: int) -> None:
        """Initialize the NegativeTimeError."""
        super().__init__(
            f"Negative time value encountered: {time}. Time must be non-negative."
        )


class InvalidRoomError(Exception):
    """Exception raised when a room is defined with invalid parameters."""

    def __init__(self, message: str) -> None:
        """Initialize the InvalidRoomError."""
        super().__init__(f"Invalid room definition: {message}.")


class InvalidDoorError(Exception):
    """Exception raised when a door is defined with invalid parameters."""

    def __init__(self, message: str) -> None:
        """Initialize the InvalidDoorError."""
        super().__init__(f"Invalid door definition: {message}.")
