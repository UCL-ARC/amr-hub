"""Module for testing extraction of polygons from dxf linework."""

from pathlib import Path
from typing import Any

import geopandas as gpd
import pytest
import yaml
from shapely.geometry import LineString, Point, Polygon

from floorplan_extractor.dxf_polygon_extraction import (
    ExtractionConfig,
    PolygonExtractionConfig,
    SharedWallConfig,
    _attach_polygon_labels,
    _flatten_z_points,
    _generate_polygons,
    config_from_yaml,
)

# Constants
POLYGON_LAYER_NAME: str = "WALLS"
LABEL_LAYER_NAME: str = "LABELS"

POLYGON_LABEL_COLUMN: str = "label"
POLYGON_LABEL_TARGET: str = "room"
FLOOR_FILTER: str = "1"

LAYER_COLUMN: str = "Layer"
GEOMETRY_COLUMN: str = "geometry"
GEOMETRY_TYPE_COLUMN: str = "geometry_type"

LINE_COORDINATES: list[list[tuple[float, float]]] = [
    [(0.0, 0.0), (1.0, 0.0)],
    [(1.0, 0.0), (1.0, 1.0)],
    [(1.0, 1.0), (0.0, 1.0)],
    [(0.0, 1.0), (0.0, 0.0)],
]

POLYGON_COORDINATES: list[tuple[float, float]] = [
    (0.0, 0.0),
    (2.0, 0.0),
    (2.0, 2.0),
    (0.0, 2.0),
]

LABEL_VALUES: list[str] = ["101", "102"]
EXPECTED_AGGREGATED_LABEL: str = "101, 102"

Z_POINT_X: float = 1.0
Z_POINT_Y: float = 2.0
Z_POINT_Z: float = 3.0
SHARED_WALL_MIN_GAP: float = 50.0
SHARED_WALL_MAX_GAP: float = 130.0
SHARED_WALL_ANGLE_TOLERANCE_DEGREES: float = 2.0
SHARED_WALL_MIN_OVERLAP_RATIO: float = 0.75
SHARED_WALL_MIN_OVERLAP_LENGTH: float = 250.0
SHARED_WALL_CANONICAL_LINE: str = "midline"


def _base_config_data() -> dict[str, Any]:
    return {
        "polygons": {
            "polygon_layer_name": POLYGON_LAYER_NAME,
            "label_layer_name": LABEL_LAYER_NAME,
            "polygon_label_column": POLYGON_LABEL_COLUMN,
            "polygon_label_target": POLYGON_LABEL_TARGET,
            "floor_filter": FLOOR_FILTER,
            "excluded_room_numbers": [],
        }
    }


def test_config_from_yaml(tmp_path: Path) -> None:
    """YAML configuration is loaded into an ExtractionConfig."""
    config_data = _base_config_data()

    config_path: Path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    config = config_from_yaml(config_path)

    assert isinstance(config, ExtractionConfig)
    assert isinstance(config.polygons, PolygonExtractionConfig)

    assert config.polygons.polygon_layer_name == POLYGON_LAYER_NAME
    assert config.polygons.label_layer_name == LABEL_LAYER_NAME
    assert config.polygons.polygon_label_column == POLYGON_LABEL_COLUMN
    assert config.polygons.polygon_label_target == POLYGON_LABEL_TARGET
    assert config.polygons.floor_filter == FLOOR_FILTER

    assert config.door_layer_name is None
    assert config.doors is None
    assert config.shared_walls is None


def test_config_from_yaml_loads_shared_wall_config(tmp_path: Path) -> None:
    """Shared-wall configuration is parsed when present."""
    config_data = _base_config_data()
    config_data["shared_walls"] = {
        "enabled": True,
        "min_gap": SHARED_WALL_MIN_GAP,
        "max_gap": SHARED_WALL_MAX_GAP,
        "angle_tolerance_degrees": SHARED_WALL_ANGLE_TOLERANCE_DEGREES,
        "min_overlap_ratio": SHARED_WALL_MIN_OVERLAP_RATIO,
        "min_overlap_length": SHARED_WALL_MIN_OVERLAP_LENGTH,
        "canonical_line": SHARED_WALL_CANONICAL_LINE,
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    config = config_from_yaml(config_path)

    assert isinstance(config.shared_walls, SharedWallConfig)
    assert config.shared_walls.enabled is True
    assert config.shared_walls.min_gap == SHARED_WALL_MIN_GAP
    assert config.shared_walls.max_gap == SHARED_WALL_MAX_GAP
    assert (
        config.shared_walls.angle_tolerance_degrees
        == SHARED_WALL_ANGLE_TOLERANCE_DEGREES
    )
    assert config.shared_walls.min_overlap_ratio == SHARED_WALL_MIN_OVERLAP_RATIO
    assert config.shared_walls.min_overlap_length == SHARED_WALL_MIN_OVERLAP_LENGTH
    assert config.shared_walls.canonical_line == SHARED_WALL_CANONICAL_LINE


def test_example_config_loads_shared_wall_config() -> None:
    """The example extraction configuration includes shared-wall settings."""
    config_path = Path(__file__).parents[1] / "config.yaml"

    config = config_from_yaml(config_path)

    assert isinstance(config.shared_walls, SharedWallConfig)
    assert config.shared_walls.enabled is True
    assert config.shared_walls.canonical_line == SHARED_WALL_CANONICAL_LINE


def test_config_from_yaml_loads_disabled_shared_wall_config(tmp_path: Path) -> None:
    """Disabled shared-wall configuration is parsed without enabling behaviour."""
    config_data = _base_config_data()
    config_data["shared_walls"] = {
        "enabled": False,
        "canonical_line": SHARED_WALL_CANONICAL_LINE,
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    config = config_from_yaml(config_path)

    assert isinstance(config.shared_walls, SharedWallConfig)
    assert config.shared_walls.enabled is False
    assert config.shared_walls.canonical_line == SHARED_WALL_CANONICAL_LINE


def test_config_from_yaml_rejects_invalid_shared_wall_canonical_line(
    tmp_path: Path,
) -> None:
    """Invalid shared-wall canonical line values fail with a clear error."""
    config_data = _base_config_data()
    config_data["shared_walls"] = {
        "enabled": True,
        "canonical_line": "left-face",
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"'shared_walls\.canonical_line' must be one of midline",
    ):
        config_from_yaml(config_path)


def test_flatten_z_points_removes_z_dimension() -> None:
    """Z-coordinates are removed from Point geometries."""
    gdf: gpd.GeoDataFrame = gpd.GeoDataFrame(
        {GEOMETRY_COLUMN: [Point(Z_POINT_X, Z_POINT_Y, Z_POINT_Z)]},
        geometry=GEOMETRY_COLUMN,
    )

    flattened: gpd.GeoDataFrame = _flatten_z_points(gdf)

    geom = flattened.geometry.iloc[0]
    assert isinstance(geom, Point)
    assert geom.has_z is False


def test_generate_polygons_from_linework() -> None:
    """Closed linework is polygonised into a single polygon."""
    lines: list[LineString] = [LineString(coords) for coords in LINE_COORDINATES]

    gdf: gpd.GeoDataFrame = gpd.GeoDataFrame(
        {
            LAYER_COLUMN: [POLYGON_LAYER_NAME] * len(lines),
            GEOMETRY_COLUMN: lines,
        },
        geometry=GEOMETRY_COLUMN,
    )

    polygons: gpd.GeoDataFrame = _generate_polygons(gdf, POLYGON_LAYER_NAME)

    assert len(polygons) == 1
    assert isinstance(polygons.geometry.iloc[0], Polygon)


def test_attach_polygon_labels_aggregates_sorted_labels() -> None:
    """Multiple labels within a polygon are aggregated deterministically."""
    polygons: gpd.GeoDataFrame = gpd.GeoDataFrame(
        {GEOMETRY_COLUMN: [Polygon(POLYGON_COORDINATES)]},
        geometry=GEOMETRY_COLUMN,
    )

    labels: gpd.GeoDataFrame = gpd.GeoDataFrame(
        {
            POLYGON_LABEL_COLUMN: LABEL_VALUES,
            GEOMETRY_COLUMN: [
                Point(0.5, 0.5),
                Point(1.5, 1.5),
            ],
        },
        geometry=GEOMETRY_COLUMN,
    )

    result: gpd.GeoDataFrame = _attach_polygon_labels(
        polygons,
        labels,
        polygon_label_column=POLYGON_LABEL_COLUMN,
        polygon_label_target=POLYGON_LABEL_TARGET,
    )

    assert result.loc[0, POLYGON_LABEL_TARGET] == EXPECTED_AGGREGATED_LABEL
    assert result.loc[0, GEOMETRY_TYPE_COLUMN] == "POLYGON"
