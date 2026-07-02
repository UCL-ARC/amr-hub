"""Module for testing extraction of polygons from dxf linework."""

from itertools import pairwise
from pathlib import Path
from typing import Any

import geopandas as gpd
import pytest
import yaml
from shapely.geometry import LineString, Point, Polygon

from floorplan_extractor.dxf_polygon_extraction import (
    DoorAttachmentConfig,
    ExtractionConfig,
    PolygonAdditionConfig,
    PolygonExtractionConfig,
    PolygonMergeConfig,
    PolygonSplitConfig,
    PolygonSplitRegionConfig,
    SharedWallConfig,
    _apply_addition_labels,
    _apply_polygon_additions,
    _apply_polygon_merges,
    _apply_polygon_splits,
    _apply_split_region_labels,
    _attach_polygon_labels,
    _flatten_z_points,
    _generate_polygons,
    _generate_room_numbers,
    attach_room_doors,
    config_from_yaml,
    extract_polygons,
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
EXPECTED_PRIMARY_LABEL: str = "101"

Z_POINT_X: float = 1.0
Z_POINT_Y: float = 2.0
Z_POINT_Z: float = 3.0
SHARED_WALL_MIN_GAP: float = 50.0
SHARED_WALL_MAX_GAP: float = 130.0
SHARED_WALL_ANGLE_TOLERANCE_DEGREES: float = 2.0
SHARED_WALL_MIN_OVERLAP_RATIO: float = 0.75
SHARED_WALL_MIN_OVERLAP_LENGTH: float = 250.0
SHARED_WALL_CANONICAL_LINE: str = "midline"
DOOR_LAYER_NAME: str = "DOORS"
DOOR_ENTITY_HANDLE: str = "door-1"


def _polygon_config() -> PolygonExtractionConfig:
    return PolygonExtractionConfig(
        polygon_layer_name=POLYGON_LAYER_NAME,
        label_layer_name=LABEL_LAYER_NAME,
        polygon_label_column=POLYGON_LABEL_COLUMN,
        polygon_label_target=POLYGON_LABEL_TARGET,
        floor_filter=FLOOR_FILTER,
        excluded_room_numbers=[],
    )


def _shared_wall_config(*, enabled: bool) -> SharedWallConfig:
    return SharedWallConfig(
        enabled=enabled,
        min_gap=SHARED_WALL_MIN_GAP,
        max_gap=SHARED_WALL_MAX_GAP,
        angle_tolerance_degrees=SHARED_WALL_ANGLE_TOLERANCE_DEGREES,
        min_overlap_ratio=SHARED_WALL_MIN_OVERLAP_RATIO,
        min_overlap_length=SHARED_WALL_MIN_OVERLAP_LENGTH,
        canonical_line=SHARED_WALL_CANONICAL_LINE,
    )


def _rectangle_lines(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> list[LineString]:
    return [
        LineString([(min_x, min_y), (max_x, min_y)]),
        LineString([(max_x, min_y), (max_x, max_y)]),
        LineString([(max_x, max_y), (min_x, max_y)]),
        LineString([(min_x, max_y), (min_x, min_y)]),
    ]


def _shared_wall_extraction_gdf() -> gpd.GeoDataFrame:
    room_boundary_lines = [
        *_rectangle_lines(0.0, 0.0, 400.0, 400.0),
        *_rectangle_lines(500.0, 0.0, 900.0, 400.0),
    ]
    rows: list[dict[str, object]] = [
        {
            LAYER_COLUMN: POLYGON_LAYER_NAME,
            "EntityHandle": None,
            POLYGON_LABEL_COLUMN: None,
            GEOMETRY_COLUMN: line,
        }
        for line in room_boundary_lines
    ]

    rows.extend(
        [
            {
                LAYER_COLUMN: LABEL_LAYER_NAME,
                "EntityHandle": None,
                POLYGON_LABEL_COLUMN: "101",
                GEOMETRY_COLUMN: Point(200.0, 200.0),
            },
            {
                LAYER_COLUMN: LABEL_LAYER_NAME,
                "EntityHandle": None,
                POLYGON_LABEL_COLUMN: "102",
                GEOMETRY_COLUMN: Point(700.0, 200.0),
            },
            {
                LAYER_COLUMN: DOOR_LAYER_NAME,
                "EntityHandle": DOOR_ENTITY_HANDLE,
                POLYGON_LABEL_COLUMN: None,
                GEOMETRY_COLUMN: LineString([(450.0, 150.0), (450.0, 250.0)]),
            },
        ]
    )

    return gpd.GeoDataFrame(rows, geometry=GEOMETRY_COLUMN)


def _canonical_segments(polygon: Polygon) -> set[tuple[tuple[float, float], ...]]:
    coords = list(polygon.exterior.coords)

    return {
        tuple(
            sorted(
                (
                    (round(start[0], 6), round(start[1], 6)),
                    (round(end[0], 6), round(end[1], 6)),
                )
            )
        )
        for start, end in pairwise(coords)
    }


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


def test_mock_config_loads_shared_wall_config() -> None:
    """The mock extraction configuration includes shared-wall settings."""
    config_path = Path(__file__).parent / "inputs" / "config.yaml"

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


def test_config_from_yaml_loads_polygon_splits(tmp_path: Path) -> None:
    """Configured polygon cut lines and region labels are parsed."""
    config_data = _base_config_data()
    config_data["polygon_splits"] = [
        {
            "selector_point": [0.5, 0.5],
            "cut_lines": [[1.0, -1.0, 1.0, 3.0]],
            "regions": [
                {"label": "101", "seed_point": [0.5, 0.5]},
                {"label": "CORRIDOR", "seed_point": [1.5, 0.5]},
            ],
        }
    ]
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    config = config_from_yaml(config_path)

    assert config.polygon_splits == [
        PolygonSplitConfig(
            selector_point=(0.5, 0.5),
            cut_lines=[(1.0, -1.0, 1.0, 3.0)],
            regions=[
                PolygonSplitRegionConfig(label="101", seed_point=(0.5, 0.5)),
                PolygonSplitRegionConfig(
                    label="CORRIDOR",
                    seed_point=(1.5, 0.5),
                ),
            ],
        )
    ]


def test_config_from_yaml_loads_polygon_additions(tmp_path: Path) -> None:
    """Explicit missing polygons and labels are parsed."""
    config_data = _base_config_data()
    config_data["polygon_additions"] = [
        {
            "label": "CORRIDOR",
            "coordinates": POLYGON_COORDINATES,
        }
    ]
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    config = config_from_yaml(config_path)

    assert config.polygon_additions == [
        PolygonAdditionConfig(
            label="CORRIDOR",
            coordinates=POLYGON_COORDINATES,
        )
    ]


def test_config_from_yaml_loads_polygon_merges(tmp_path: Path) -> None:
    """Configured source labels and target label are parsed."""
    config_data = _base_config_data()
    config_data["polygon_merges"] = [
        {
            "target_label": "101",
            "source_labels": ["CORRIDOR"],
        }
    ]
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    config = config_from_yaml(config_path)

    assert config.polygon_merges == [
        PolygonMergeConfig(
            target_label="101",
            source_labels=["CORRIDOR"],
        )
    ]


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


def test_extract_polygons_applies_enabled_shared_wall_normalisation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Enabled shared-wall normalisation runs before door attachment."""
    monkeypatch.setattr(
        gpd,
        "read_file",
        lambda _: _shared_wall_extraction_gdf(),
    )
    config = ExtractionConfig(
        polygons=_polygon_config(),
        door_layer_name=DOOR_LAYER_NAME,
        doors=DoorAttachmentConfig(),
        shared_walls=_shared_wall_config(enabled=True),
    )

    result = extract_polygons(tmp_path / "floorplan.dxf", config)

    expected_midline = ((450.0, 0.0), (450.0, 400.0))
    assert tuple(sorted(expected_midline)) in _canonical_segments(
        result.geometry.iloc[0]
    )
    assert tuple(sorted(expected_midline)) in _canonical_segments(
        result.geometry.iloc[1]
    )
    assert result["shared_wall_count"].to_list() == [1, 1]
    assert result["shared_wall_review"].to_list() == [False, False]
    assert result["door_count"].to_list() == [1, 1]
    assert result["doors"].apply(bool).to_list() == [True, True]
    assert result["needs_review"].to_list() == [False, False]


def test_extract_polygons_preserves_shape_when_shared_walls_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Disabled shared-wall configuration leaves extraction output current-style."""
    monkeypatch.setattr(
        gpd,
        "read_file",
        lambda _: _shared_wall_extraction_gdf(),
    )
    config = ExtractionConfig(
        polygons=_polygon_config(),
        door_layer_name=DOOR_LAYER_NAME,
        doors=DoorAttachmentConfig(),
        shared_walls=_shared_wall_config(enabled=False),
    )

    result = extract_polygons(tmp_path / "floorplan.dxf", config)

    assert tuple(sorted(((400.0, 0.0), (400.0, 400.0)))) in _canonical_segments(
        result.geometry.iloc[0]
    )
    assert tuple(sorted(((500.0, 0.0), (500.0, 400.0)))) in _canonical_segments(
        result.geometry.iloc[1]
    )
    assert "shared_wall_count" not in result.columns
    assert "shared_wall_review" not in result.columns
    assert "shared_wall_rejections" not in result.columns
    assert result["door_count"].to_list() == [0, 0]


def test_attach_room_doors_projects_door_symbol_onto_shared_wall() -> None:
    """Door symbols become one canonical segment on the shared wall."""
    rooms = gpd.GeoDataFrame(
        {
            GEOMETRY_COLUMN: [
                Polygon([(0.0, 0.0), (5.0, 0.0), (5.0, 10.0), (0.0, 10.0)]),
                Polygon([(5.0, 0.0), (10.0, 0.0), (10.0, 10.0), (5.0, 10.0)]),
            ]
        },
        geometry=GEOMETRY_COLUMN,
    )
    doors = gpd.GeoDataFrame(
        {
            "EntityHandle": [DOOR_ENTITY_HANDLE] * 3,
            GEOMETRY_COLUMN: [
                LineString([(5.0, 4.0), (8.0, 4.0)]),
                LineString([(5.0, 6.0), (8.0, 6.0)]),
                LineString([(8.0, 4.0), (7.0, 5.5), (5.0, 6.0)]),
            ],
        },
        geometry=GEOMETRY_COLUMN,
    )

    result = attach_room_doors(rooms, doors)

    expected_door = [5.0, 4.0, 5.0, 6.0]
    assert result["doors"].to_list() == [[expected_door], [expected_door]]
    for room_id, door_values in result["doors"].items():
        door_line = LineString(
            [(door_values[0][0], door_values[0][1]), door_values[0][2:]]
        )
        assert door_line.difference(result.geometry.iloc[room_id].boundary).is_empty


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


def test_polygon_split_creates_and_labels_configured_regions() -> None:
    """Configured cut lines create regions with explicit labels."""
    polygons = gpd.GeoDataFrame(
        {GEOMETRY_COLUMN: [Polygon(POLYGON_COORDINATES)]},
        geometry=GEOMETRY_COLUMN,
    )
    split_config = PolygonSplitConfig(
        selector_point=(0.5, 0.5),
        cut_lines=[(1.0, -1.0, 1.0, 3.0)],
        regions=[
            PolygonSplitRegionConfig(label="101", seed_point=(0.5, 0.5)),
            PolygonSplitRegionConfig(label="CORRIDOR", seed_point=(1.5, 0.5)),
        ],
    )

    split_polygons = _apply_polygon_splits(polygons, [split_config])
    labelled_polygons = split_polygons.assign(
        **{
            POLYGON_LABEL_TARGET: None,
            "label_candidates": [[] for _ in range(len(split_polygons))],
            "label_count": 0,
            "label_ambiguous": False,
        }
    )
    result = _apply_split_region_labels(
        labelled_polygons,
        [split_config],
        POLYGON_LABEL_TARGET,
    )

    assert len(result) == 2
    assert set(result[POLYGON_LABEL_TARGET]) == {"101", "CORRIDOR"}
    assert result["label_count"].to_list() == [1, 1]
    assert result["label_ambiguous"].to_list() == [False, False]


def test_polygon_addition_creates_and_labels_missing_region() -> None:
    """Configured additions create explicitly labelled polygons."""
    polygons = gpd.GeoDataFrame(
        {GEOMETRY_COLUMN: []},
        geometry=GEOMETRY_COLUMN,
    )
    addition_config = PolygonAdditionConfig(
        label="CORRIDOR",
        coordinates=POLYGON_COORDINATES,
    )

    added_polygons = _apply_polygon_additions(polygons, [addition_config])
    labelled_polygons = added_polygons.assign(
        **{
            POLYGON_LABEL_TARGET: None,
            "label_candidates": [[]],
            "label_count": 0,
            "label_ambiguous": False,
        }
    )
    result = _apply_addition_labels(
        labelled_polygons,
        [addition_config],
        POLYGON_LABEL_TARGET,
    )

    assert len(result) == 1
    assert result.loc[0, POLYGON_LABEL_TARGET] == "CORRIDOR"
    assert result.loc[0, "label_candidates"] == ["CORRIDOR"]
    assert result.loc[0, "label_count"] == 1
    assert not result.loc[0, "label_ambiguous"]


def test_polygon_merge_combines_multiple_source_polygons() -> None:
    """All matching source polygons are absorbed into the target polygon."""
    polygons = gpd.GeoDataFrame(
        {
            POLYGON_LABEL_TARGET: ["101", "CORRIDOR", "CORRIDOR"],
            "label_candidates": [["101"], ["CORRIDOR"], ["CORRIDOR"]],
            "label_count": [1, 1, 1],
            "label_ambiguous": [False, False, False],
            GEOMETRY_COLUMN: [
                Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),
                Polygon([(2, 0), (3, 0), (3, 1), (2, 1)]),
            ],
        },
        geometry=GEOMETRY_COLUMN,
    )

    result = _apply_polygon_merges(
        polygons,
        [PolygonMergeConfig(target_label="101", source_labels=["CORRIDOR"])],
        POLYGON_LABEL_TARGET,
    )

    assert len(result) == 1
    assert result.loc[0, POLYGON_LABEL_TARGET] == "101"
    assert result.loc[0, "label_candidates"] == ["101"]
    assert result.loc[0, "label_count"] == 1
    assert not result.loc[0, "label_ambiguous"]
    assert result.geometry.iloc[0].area == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("labels", "geometries", "expected_message"),
    [
        (
            ["CORRIDOR"],
            [Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])],
            "target must identify exactly one polygon",
        ),
        (
            ["101", "101", "CORRIDOR"],
            [
                Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                Polygon([(0, 1), (1, 1), (1, 2), (0, 2)]),
                Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),
            ],
            "target must identify exactly one polygon",
        ),
        (
            ["101"],
            [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
            "source must identify at least one polygon",
        ),
        (
            ["101", "CORRIDOR"],
            [
                Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                Polygon([(2, 0), (3, 0), (3, 1), (2, 1)]),
            ],
            "must produce one valid Polygon",
        ),
    ],
)
def test_polygon_merge_rejects_invalid_selection_or_geometry(
    labels: list[str],
    geometries: list[Polygon],
    expected_message: str,
) -> None:
    """Invalid or disconnected merge selections fail rather than losing geometry."""
    polygons = gpd.GeoDataFrame(
        {
            POLYGON_LABEL_TARGET: labels,
            "label_candidates": [[label] for label in labels],
            "label_count": [1] * len(labels),
            "label_ambiguous": [False] * len(labels),
            GEOMETRY_COLUMN: geometries,
        },
        geometry=GEOMETRY_COLUMN,
    )

    with pytest.raises(ValueError, match=expected_message):
        _apply_polygon_merges(
            polygons,
            [PolygonMergeConfig(target_label="101", source_labels=["CORRIDOR"])],
            POLYGON_LABEL_TARGET,
        )


def test_extract_polygons_applies_merges_before_shared_walls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Shared-wall normalisation receives the final merged room geometry."""
    monkeypatch.setattr(
        gpd,
        "read_file",
        lambda _: _shared_wall_extraction_gdf(),
    )
    observed_labels: list[str] = []

    def record_shared_wall_input(
        rooms: gpd.GeoDataFrame,
        _config: SharedWallConfig,
    ) -> gpd.GeoDataFrame:
        observed_labels.extend(rooms[POLYGON_LABEL_TARGET].to_list())
        return rooms

    monkeypatch.setattr(
        "floorplan_extractor.dxf_polygon_extraction.normalise_shared_walls",
        record_shared_wall_input,
    )
    config = ExtractionConfig(
        polygons=_polygon_config(),
        shared_walls=_shared_wall_config(enabled=True),
        polygon_additions=[
            PolygonAdditionConfig(
                label="CORRIDOR",
                coordinates=[
                    (400.0, 0.0),
                    (500.0, 0.0),
                    (500.0, 400.0),
                    (400.0, 400.0),
                ],
            )
        ],
        polygon_merges=[
            PolygonMergeConfig(
                target_label="101",
                source_labels=["CORRIDOR"],
            )
        ],
    )

    result = extract_polygons(tmp_path / "floorplan.dxf", config)

    assert observed_labels == ["101", "102"]
    assert result[POLYGON_LABEL_TARGET].to_list() == ["101", "102"]
    target_geometry = result.loc[
        result[POLYGON_LABEL_TARGET] == "101",
        "geometry",
    ].iloc[0]
    assert target_geometry.area == pytest.approx(200000.0)


def test_generate_room_numbers_extracts_codes_from_multiline_labels() -> None:
    """Room codes are extracted regardless of their line within label text."""
    gdf = gpd.GeoDataFrame(
        {
            LAYER_COLUMN: [LABEL_LAYER_NAME] * 3,
            POLYGON_LABEL_COLUMN: [
                "STORE\n101",
                "102\nLINEN",
                "OTHER FLOOR\n201",
            ],
            GEOMETRY_COLUMN: [
                Point(0.0, 0.0),
                Point(1.0, 1.0),
                Point(2.0, 2.0),
            ],
        },
        geometry=GEOMETRY_COLUMN,
    )

    result = _generate_room_numbers(
        gdf,
        label_layer_name=LABEL_LAYER_NAME,
        floor_filter=FLOOR_FILTER,
        polygon_label_column=POLYGON_LABEL_COLUMN,
        excluded_room_numbers=[],
    )

    assert result[POLYGON_LABEL_COLUMN].to_list() == ["101", "102"]


def test_generate_room_numbers_excludes_normalised_multiline_codes() -> None:
    """Exclusions apply after a room code is extracted from multiline text."""
    excluded_label = "101"
    gdf = gpd.GeoDataFrame(
        {
            LAYER_COLUMN: [LABEL_LAYER_NAME],
            POLYGON_LABEL_COLUMN: [f"STORE\n{excluded_label}"],
            GEOMETRY_COLUMN: [Point(0.0, 0.0)],
        },
        geometry=GEOMETRY_COLUMN,
    )

    result = _generate_room_numbers(
        gdf,
        label_layer_name=LABEL_LAYER_NAME,
        floor_filter=FLOOR_FILTER,
        polygon_label_column=POLYGON_LABEL_COLUMN,
        excluded_room_numbers=[excluded_label],
    )

    assert result.empty


def test_attach_polygon_labels_selects_primary_label_and_records_ambiguity() -> None:
    """Multiple labels produce one primary label and ambiguity diagnostics."""
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

    assert result.loc[0, POLYGON_LABEL_TARGET] == EXPECTED_PRIMARY_LABEL
    assert result.loc[0, "label_candidates"] == LABEL_VALUES
    assert result.loc[0, "label_count"] == len(LABEL_VALUES)
    assert result.loc[0, "label_ambiguous"]
    assert result.loc[0, GEOMETRY_TYPE_COLUMN] == "POLYGON"
