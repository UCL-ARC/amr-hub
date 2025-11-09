"""Module defining all custom exceptions for the AMR Hub ABM simulation."""


class InvalidDistanceError(Exception):
    """Exception raised when an invalid distance calculation is attempted."""

    def __init__(self, floors: tuple[int, int]) -> None:
        """Initialize the InvalidDistanceError."""
        super().__init__(
            f"Invalid distance calculation between floors: {floors[0]} and {floors[1]}."
        )


class NegativeTimeError(Exception):
    """Exception raised when a negative time value is encountered."""

    def __init__(self, time: int) -> None:
        """Initialize the NegativeTimeError."""
        super().__init__(
            f"Negative time value encountered: {time}. Time must be non-negative."
        )
