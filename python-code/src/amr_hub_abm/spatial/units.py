"""Canonical spatial units used by simulation input and runtime geometry."""

from enum import StrEnum

SPATIAL_SCHEMA_VERSION = 1


class CoordinateUnit(StrEnum):
    """Supported coordinate units for canonical spatial input."""

    METRE = "m"
