"""Deterministic assertions for local Cartesian floorplan geometry."""

from collections.abc import Iterable

import pytest
import shapely
from shapely.geometry.base import BaseGeometry

FLOORPLAN_GEOMETRY_TOLERANCE = 1e-6


def assert_geometry_equal(
    actual: BaseGeometry,
    expected: BaseGeometry,
    *,
    tolerance: float = FLOORPLAN_GEOMETRY_TOLERANCE,
) -> None:
    """
    Assert geometries are structurally equal within a local-coordinate tolerance.

    Shapely normalisation makes coordinate ordering deterministic before exact
    comparison. The default tolerance is one millionth of a floorplan coordinate
    unit, which absorbs floating-point projection noise without hiding material
    geometry changes.

    Parameters
    ----------
    actual : shapely.geometry.base.BaseGeometry
        Geometry produced by the extraction pipeline.
    expected : shapely.geometry.base.BaseGeometry
        Regression baseline geometry.
    tolerance : float
        Maximum coordinate difference in local floorplan units.

    """
    if shapely.equals_exact(actual, expected, tolerance=tolerance, normalize=True):
        return

    pytest.fail(
        "Geometry differs from regression baseline:\n"
        f"actual={actual.wkt}\n"
        f"expected={expected.wkt}\n"
        f"tolerance={tolerance}"
    )


def rounded_optional(value: float | None, *, digits: int = 6) -> float | None:
    """Round optional numeric diagnostic values for deterministic comparison."""
    if isinstance(value, float):
        return round(value, digits)
    return value


def sorted_records(records: Iterable[tuple[object, ...]]) -> list[tuple[object, ...]]:
    """Return diagnostic tuples in deterministic string-key order."""
    return sorted(records, key=repr)
