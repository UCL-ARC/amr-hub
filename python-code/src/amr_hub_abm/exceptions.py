"""
Module defining all custom exceptions for the AMR Hub ABM simulation.

The exceptions defined in this module are

- SimulationModeError: When an operation is invalid for the given simulation mode.
- InvalidDistanceError: When an invalid distance calculation is attempted.
- TimeError: When a negative time value is encountered.
- InvalidRoomError: When a room is defined with invalid parameters.
- InvalidDoorError: When a door is defined with invalid parameters.
- InvalidDefinitionError: When a general invalid definition is encountered.
"""


class SimulationModeError(Exception):
    """
    Exception raised when an operation is invalid for the current simulation mode.

    This exception is used to indicate that a certain action or operation cannot be
    performed because it is not compatible with the current simulation mode.

    Attributes
    ----------
        message (str): A description of the error that occurred.

    """

    def __init__(self, message: str) -> None:
        """Initialize the SimulationModeError."""
        super().__init__(f"Simulation mode error: {message}.")


class InvalidDistanceError(Exception):
    """
    Exception raised when an invalid distance calculation is attempted.

    This exception is used to indicate that a distance calculation between two locations
    is invalid, either because the locations are not compatible
    (e.g., different buildings).

    Attributes
    ----------
        locations (tuple): A tuple containing the two locations involved in the distance
        calculation.

        building (bool): A flag indicating whether the distance calculation is between
        buildings (True) or floors (False).

    """

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


class TimeError(Exception):
    """
    Exception raised when a negative time value is encountered.

    This exception is used to indicate that a time value provided to a function or
    method is negative, which is invalid in the context of the simulation.

    Attributes
    ----------
        message (str): A description of the error that occurred.

    """

    def __init__(self, message: str) -> None:
        """Initialize the TimeError."""
        super().__init__(f"Invalid time value encountered: {message}.")


class InvalidRoomError(Exception):
    """
    Exception raised when a room is defined with invalid parameters.

    This exception is used to indicate that a room definition is invalid, either
    because of missing parameters, incompatible parameters, or other issues with the
    room definition.

    Attributes
    ----------
        message (str): A description of the error that occurred.

    """

    def __init__(self, message: str) -> None:
        """Initialize the InvalidRoomError."""
        super().__init__(f"Invalid room definition: {message}.")


class InvalidDoorError(Exception):
    """
    Exception raised when a door is defined with invalid parameters.

    Attributes
    ----------
        message (str): A description of the error that occurred.

    """

    def __init__(self, message: str) -> None:
        """Initialize the InvalidDoorError."""
        super().__init__(f"Invalid door definition: {message}.")


class InvalidDefinitionError(Exception):
    """
    Exception raised when a general invalid definition is encountered.

    Attributes
    ----------
        message (str): A description of the error that occurred.

    """

    def __init__(self, message: str) -> None:
        """Initialize the InvalidDefinitionError."""
        super().__init__(f"Invalid definition: {message}.")
