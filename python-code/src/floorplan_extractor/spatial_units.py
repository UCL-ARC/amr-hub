"""Source-unit configuration for canonical floorplan serialisation."""

from dataclasses import dataclass
from math import isfinite

from amr_hub_abm.exceptions import InvalidDefinitionError


@dataclass(frozen=True)
class SpatialUnits:
    """
    Define how source floorplan coordinates convert to metres.

    Parameters
    ----------
    source_unit : str
        Human-readable source-unit name retained as provenance.
    units_per_metre : float
        Number of source coordinate units in one metre.

    """

    source_unit: str
    units_per_metre: float

    def __post_init__(self) -> None:
        """Validate the explicit source-unit contract."""
        if not isinstance(self.source_unit, str) or not self.source_unit.strip():
            msg = "spatial_units.source_unit must be a non-empty string"
            raise InvalidDefinitionError(msg)
        if isinstance(self.units_per_metre, bool) or not isinstance(
            self.units_per_metre, (int, float)
        ):
            msg = "spatial_units.units_per_metre must be a positive finite number"
            raise InvalidDefinitionError(msg)
        units_per_metre = float(self.units_per_metre)
        if not isfinite(units_per_metre) or units_per_metre <= 0:
            msg = "spatial_units.units_per_metre must be a positive finite number"
            raise InvalidDefinitionError(msg)

        object.__setattr__(self, "source_unit", self.source_unit.strip())
        object.__setattr__(self, "units_per_metre", units_per_metre)

    def to_metres(self, value: float) -> float:
        """Convert one linear source-coordinate value to metres."""
        return float(value) / self.units_per_metre

    def area_to_square_metres(self, value: float) -> float:
        """Convert one source-coordinate area to square metres."""
        return float(value) / self.units_per_metre**2
