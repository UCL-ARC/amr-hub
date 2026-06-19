"""
DXF floorplan polygon extraction and labelling.

This module provides utilities for extracting closed polygon geometries
from DXF floorplan linework and attaching textual room labels to those
polygons using spatial point-in-polygon relationships.

The intended use case is indoor floorplans where all geometries exist in
a single, local Cartesian coordinate space. No coordinate reference system
(CRS) is assumed or required. All spatial operations are therefore purely
topological.

Typical workflow:
1. Read a DXF file into a GeoDataFrame.
2. Polygonise linework from a specified DXF layer.
3. Extract room label point geometries from another layer.
4. Filter labels by floor using a string prefix.
5. Spatially join labels to polygons and aggregate them deterministically.

The module makes the following assumptions:
- DXF layer names are stable and known in advance.
- A column named "Layer" is present in the input GeoDataFrame.
- Room labels are stored as point geometries.
- Multiple labels may fall within a single polygon and will be
  concatenated in sorted order.

The public entry point is `extract_polygons`. All other functions are
internal helpers and are not part of the public API.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import shapely
import yaml
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, polygonize, split, unary_union

from floorplan_extractor.shared_walls import SharedWallConfig, normalise_shared_walls

XY = tuple[float, float]
DoorQuad = list[float]  # [x1, y1, x2, y2]
CutLine = tuple[float, float, float, float]
MIN_DOOR_ENDPOINTS: int = 2
VALID_SHARED_WALL_CANONICAL_LINES: frozenset[str] = frozenset({"midline"})


@dataclass(frozen=True)
class PolygonExtractionConfig:
    """
    Configuration for DXF polygon extraction and labelling.

    Attributes
    ----------
    polygon_layer_name : str
        Name of the DXF layer containing polygon boundary linework.
    label_layer_name : str
        Name of the DXF layer containing room label point geometries.
    polygon_label_column : str
        Name of the column containing room label text.
    polygon_label_target : str
        Name of the output column to store aggregated polygon labels.
    floor_filter : str
        Prefix used to select labels belonging to a specific floor.
    excluded_room_numbers : list[str]
        List of room numbers to exclude from labelling.

    """

    polygon_layer_name: str
    label_layer_name: str
    polygon_label_column: str
    polygon_label_target: str
    floor_filter: str
    excluded_room_numbers: list[str]


@dataclass(frozen=True)
class DoorAttachmentConfig:
    """
    Configuration for extracting and attaching paired door endpoints.

    Attributes
    ----------
    entity_col : str
        Column linking the two rows that represent the same door.
    x_col : str
        Column containing centroid x coordinates.
    y_col : str
        Column containing centroid y coordinates.
    out_col : str
        Name of the output column added to the room polygons.
    predicate : str
        Spatial predicate passed to ``geopandas.sjoin``.

    """

    entity_col: str = "EntityHandle"
    x_col: str = "x"
    y_col: str = "y"
    out_col: str = "doors"
    predicate: str = "intersects"
    boundary_tolerance: float = 0.1
    min_door_length: float = 0.2
    max_attached_rooms: int = 2


@dataclass(frozen=True)
class PolygonSplitRegionConfig:
    """Explicit label for one region produced by a configured polygon split."""

    label: str
    seed_point: XY


@dataclass(frozen=True)
class PolygonSplitConfig:
    """Configuration for splitting one polygon at known floorplan boundaries."""

    selector_point: XY
    cut_lines: list[CutLine]
    regions: list[PolygonSplitRegionConfig]


@dataclass(frozen=True)
class PolygonAdditionConfig:
    """Explicit polygon missing from source room-area linework."""

    label: str
    coordinates: list[XY]


@dataclass(frozen=True)
class PolygonMergeConfig:
    """Configuration for merging labelled polygons into one target polygon."""

    target_label: str
    source_labels: list[str]


@dataclass(frozen=True)
class ExtractionConfig:
    """
    Top-level configuration for DXF extraction.

    Attributes
    ----------
    polygons : PolygonExtractionConfig
        Configuration controlling polygon generation and label attachment.
    door_layer_name : str
        Name of the DXF layer containing door geometries.
    doors : DoorAttachmentConfig or None
        If provided, doors are extracted and attached to polygons.
    shared_walls : SharedWallConfig or None
        If provided and enabled, shared-wall normalisation may be applied by
        downstream processing.
    polygon_splits : list[PolygonSplitConfig]
        Floorplan-specific polygon splits applied before label attachment.
    polygon_additions : list[PolygonAdditionConfig]
        Floorplan-specific polygons added before label attachment.
    polygon_merges : list[PolygonMergeConfig]
        Floorplan-specific labelled polygons merged before geometry normalisation.

    """

    polygons: PolygonExtractionConfig
    door_layer_name: str | None = None
    doors: DoorAttachmentConfig | None = None
    shared_walls: SharedWallConfig | None = None
    polygon_splits: list[PolygonSplitConfig] = field(default_factory=list)
    polygon_additions: list[PolygonAdditionConfig] = field(default_factory=list)
    polygon_merges: list[PolygonMergeConfig] = field(default_factory=list)


def config_from_yaml(path: Path) -> ExtractionConfig:
    """
    Load extraction configuration from a YAML file.

    Expected YAML structure
    -----------------------

    polygons:
      polygon_layer_name: ...
      label_layer_name: ...
      polygon_label_column: ...
      polygon_label_target: ...
      floor_filter: ...
      excluded_room_numbers: [...]

    doors:                       # optional
      layer_name: DOORS
      entity_col: EntityHandle
      x_col: x
      y_col: y
      out_col: doors
      predicate: intersects

    shared_walls:                # optional
      enabled: true
      min_gap: 50
      max_gap: 130
      angle_tolerance_degrees: 2
      min_overlap_ratio: 0.75
      min_overlap_length: 250
      canonical_line: midline

    polygon_splits:              # optional
      - selector_point: [x, y]
        cut_lines:
          - [x1, y1, x2, y2]
        regions:
          - label: ROOM_CODE
            seed_point: [x, y]

    polygon_additions:           # optional
      - label: CORRIDOR
        coordinates:
          - [x, y]

    polygon_merges:              # optional
      - target_label: ROOM_CODE
        source_labels: [CORRIDOR]

    Parameters
    ----------
    path : pathlib.Path
        Path to the YAML configuration file.

    Returns
    -------
    ExtractionConfig
        Parsed and validated configuration object.

    Raises
    ------
    TypeError
        If the YAML structure is invalid.
    KeyError
        If required keys are missing.

    """
    with path.open(encoding="utf-8") as f:
        data: Any = yaml.safe_load(f)

    if not isinstance(data, dict):
        msg = "YAML configuration must be a mapping"
        raise TypeError(msg)

    if "polygons" not in data:
        msg = "Missing required 'polygons' configuration block"
        raise KeyError(msg)

    polygons_cfg = PolygonExtractionConfig(**data["polygons"])

    door_layer_name: str | None = None
    door_config: DoorAttachmentConfig | None = None
    shared_wall_config: SharedWallConfig | None = None

    if "doors" in data:
        door_block = data["doors"]

        if not isinstance(door_block, dict):
            msg = "'doors' block must be a mapping"
            raise TypeError(msg)

        if "layer_name" not in door_block:
            msg = "'doors.layer_name' is required when doors block is present"
            raise KeyError(msg)

        door_layer_name = str(door_block["layer_name"])

        door_config = DoorAttachmentConfig(
            entity_col=door_block.get("entity_col", "EntityHandle"),
            x_col=door_block.get("x_col", "x"),
            y_col=door_block.get("y_col", "y"),
            out_col=door_block.get("out_col", "doors"),
            predicate=door_block.get("predicate", "intersects"),
        )

    if "shared_walls" in data:
        shared_wall_block = data["shared_walls"]

        if not isinstance(shared_wall_block, dict):
            msg = "'shared_walls' block must be a mapping"
            raise TypeError(msg)

        canonical_line = str(shared_wall_block.get("canonical_line", "midline"))
        if canonical_line not in VALID_SHARED_WALL_CANONICAL_LINES:
            valid_values = ", ".join(sorted(VALID_SHARED_WALL_CANONICAL_LINES))
            msg = (
                "'shared_walls.canonical_line' must be one of "
                f"{valid_values}; got {canonical_line!r}"
            )
            raise ValueError(msg)

        shared_wall_config = SharedWallConfig(
            enabled=bool(shared_wall_block.get("enabled", False)),
            min_gap=float(shared_wall_block.get("min_gap", 50.0)),
            max_gap=float(shared_wall_block.get("max_gap", 130.0)),
            angle_tolerance_degrees=float(
                shared_wall_block.get("angle_tolerance_degrees", 2.0)
            ),
            min_overlap_ratio=float(shared_wall_block.get("min_overlap_ratio", 0.75)),
            min_overlap_length=float(
                shared_wall_block.get("min_overlap_length", 250.0)
            ),
            canonical_line=canonical_line,
        )

    polygon_splits, polygon_additions, polygon_merges = _parse_polygon_corrections(data)

    return ExtractionConfig(
        polygons=polygons_cfg,
        door_layer_name=door_layer_name,
        doors=door_config,
        shared_walls=shared_wall_config,
        polygon_splits=polygon_splits,
        polygon_additions=polygon_additions,
        polygon_merges=polygon_merges,
    )


def _parse_polygon_corrections(
    data: dict[str, Any],
) -> tuple[
    list[PolygonSplitConfig],
    list[PolygonAdditionConfig],
    list[PolygonMergeConfig],
]:
    """Parse optional floorplan-specific polygon correction blocks."""
    split_blocks = data.get("polygon_splits", [])
    if not isinstance(split_blocks, list):
        msg = "'polygon_splits' block must be a list"
        raise TypeError(msg)

    addition_blocks = data.get("polygon_additions", [])
    if not isinstance(addition_blocks, list):
        msg = "'polygon_additions' block must be a list"
        raise TypeError(msg)

    merge_blocks = data.get("polygon_merges", [])
    if not isinstance(merge_blocks, list):
        msg = "'polygon_merges' block must be a list"
        raise TypeError(msg)

    return (
        [_parse_polygon_split(block) for block in split_blocks],
        [_parse_polygon_addition(block) for block in addition_blocks],
        [_parse_polygon_merge(block) for block in merge_blocks],
    )


def _parse_xy(value: object, field_name: str) -> XY:
    """Parse one configured two-dimensional point."""
    if not isinstance(value, list) or len(value) != 2:
        msg = f"'{field_name}' must contain exactly two coordinates"
        raise ValueError(msg)

    return (float(value[0]), float(value[1]))


def _parse_polygon_split(block: object) -> PolygonSplitConfig:
    """Parse one configured polygon split."""
    if not isinstance(block, dict):
        msg = "Each 'polygon_splits' entry must be a mapping"
        raise TypeError(msg)

    selector_point = _parse_xy(block.get("selector_point"), "selector_point")

    raw_cut_lines = block.get("cut_lines")
    if not isinstance(raw_cut_lines, list) or not raw_cut_lines:
        msg = "'cut_lines' must be a non-empty list"
        raise ValueError(msg)
    cut_lines: list[CutLine] = []
    for line in raw_cut_lines:
        if not isinstance(line, list) or len(line) != 4:
            msg = "Each 'cut_lines' entry must contain exactly four coordinates"
            raise ValueError(msg)
        cut_lines.append(
            (
                float(line[0]),
                float(line[1]),
                float(line[2]),
                float(line[3]),
            )
        )

    raw_regions = block.get("regions")
    if not isinstance(raw_regions, list) or not raw_regions:
        msg = "'regions' must be a non-empty list"
        raise ValueError(msg)
    regions: list[PolygonSplitRegionConfig] = []
    for region in raw_regions:
        if not isinstance(region, dict) or "label" not in region:
            msg = "Each split region requires 'label' and 'seed_point'"
            raise ValueError(msg)
        regions.append(
            PolygonSplitRegionConfig(
                label=str(region["label"]),
                seed_point=_parse_xy(region.get("seed_point"), "seed_point"),
            )
        )

    return PolygonSplitConfig(
        selector_point=selector_point,
        cut_lines=cut_lines,
        regions=regions,
    )


def _parse_polygon_addition(block: object) -> PolygonAdditionConfig:
    """Parse one explicitly configured polygon."""
    if not isinstance(block, dict) or "label" not in block:
        msg = "Each polygon addition requires 'label' and 'coordinates'"
        raise ValueError(msg)

    raw_coordinates = block.get("coordinates")
    if not isinstance(raw_coordinates, list) or len(raw_coordinates) < 3:
        msg = "Polygon addition 'coordinates' must contain at least three points"
        raise ValueError(msg)

    return PolygonAdditionConfig(
        label=str(block["label"]),
        coordinates=[
            _parse_xy(coordinate, "coordinates") for coordinate in raw_coordinates
        ],
    )


def _parse_polygon_merge(block: object) -> PolygonMergeConfig:
    """Parse one configured merge of labelled polygons."""
    if not isinstance(block, dict):
        msg = "Each 'polygon_merges' entry must be a mapping"
        raise TypeError(msg)

    target_label = block.get("target_label")
    if not isinstance(target_label, str) or not target_label.strip():
        msg = "Polygon merge 'target_label' must be a non-empty string"
        raise ValueError(msg)

    source_labels = block.get("source_labels")
    if (
        not isinstance(source_labels, list)
        or not source_labels
        or not all(isinstance(label, str) and label.strip() for label in source_labels)
    ):
        msg = "Polygon merge 'source_labels' must be a non-empty list of strings"
        raise ValueError(msg)

    clean_target = target_label.strip()
    clean_sources = [label.strip() for label in source_labels]
    if clean_target in clean_sources:
        msg = "Polygon merge target cannot also be a source label"
        raise ValueError(msg)

    return PolygonMergeConfig(
        target_label=clean_target,
        source_labels=clean_sources,
    )


def _pair_points_to_quad(points: list[XY]) -> DoorQuad | None:
    """
    Convert paired (x, y) points into a flattened door quad.

    Parameters
    ----------
    points : list[tuple[float, float]]
        List of (x, y) coordinate pairs belonging to the same physical door.

    Returns
    -------
    list[float] or None
        Flattened list ``[x1, y1, x2, y2]`` if at least two points are present.
        Returns ``None`` if fewer than two points are available.

    Notes
    -----
    If more than two points are provided, the first two after deterministic
    sorting are used. Ordering is purely deterministic and has no geometric
    meaning.

    """
    if len(points) < MIN_DOOR_ENDPOINTS:
        return None

    (x1, y1), (x2, y2) = sorted(points)[:2]
    return [x1, y1, x2, y2]


def _line_to_xyxy(line: BaseGeometry) -> DoorQuad | None:
    if line.is_empty:
        return None

    if isinstance(line, MultiLineString):
        merged = linemerge(line)
        if isinstance(merged, MultiLineString):
            line = max(merged.geoms, key=lambda g: g.length)
        else:
            line = merged

    if not isinstance(line, LineString):
        return None

    coords = list(line.coords)
    if len(coords) < 2:
        return None

    x1, y1 = coords[0][:2]
    x2, y2 = coords[-1][:2]

    return [float(x1), float(y1), float(x2), float(y2)]


def _combine_door_geometries(
    doors: gpd.GeoDataFrame,
    config: DoorAttachmentConfig,
) -> gpd.GeoDataFrame:
    rows = []

    for entity_id, group in doors.groupby(config.entity_col, sort=False):
        geom = unary_union(list(group.geometry))
        geom = shapely.force_2d(geom)

        if geom.length < config.min_door_length:
            continue

        door_quad = _line_to_xyxy(geom)
        if door_quad is None:
            continue

        rows.append(
            {
                config.entity_col: entity_id,
                "geometry": geom,
                "door_xyxy": door_quad,
            }
        )

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=doors.crs)


def attach_room_doors(
    labelled_polygons: gpd.GeoDataFrame,
    doors: gpd.GeoDataFrame,
    config: DoorAttachmentConfig | None = None,
) -> gpd.GeoDataFrame:
    """
    Attach paired door endpoint coordinates to room polygons.

    Parameters
    ----------
    labelled_polygons : geopandas.GeoDataFrame
        GeoDataFrame containing room polygon geometries. The index is used as
        the room identifier.
    doors : geopandas.GeoDataFrame
        GeoDataFrame containing door geometries, with two rows per physical
        door.
    config : DoorAttachmentConfig, default DoorAttachmentConfig()
        Configuration controlling the join predicate, column names, and output
        column name.

    Returns
    -------
    geopandas.GeoDataFrame
        Copy of ``labelled_polygons`` with an added column ``config.out_col``.
        Each value is a list of ``[x1, y1, x2, y2]`` lists. Rooms with no doors
        contain an empty list.

    Raises
    ------
    KeyError
        If required columns are missing from either input GeoDataFrame.

    """
    if config is None:
        config = DoorAttachmentConfig()

    required_doors_cols = {config.entity_col, "geometry"}
    missing = required_doors_cols.difference(doors.columns)
    if missing:
        msg = f"doors is missing required columns: {sorted(missing)}"
        raise KeyError(msg)

    if "geometry" not in labelled_polygons.columns:
        msg = "labelled_polygons must have a 'geometry' column"
        raise KeyError(msg)

    source_attrs = dict(labelled_polygons.attrs)
    combined_doors = _combine_door_geometries(doors, config)

    rooms = labelled_polygons.copy()
    rooms["_room_idx"] = rooms.index
    rooms["_boundary_geometry"] = rooms.geometry.boundary.buffer(
        config.boundary_tolerance
    )

    boundary_gdf = gpd.GeoDataFrame(
        rooms[["_room_idx"]],
        geometry=rooms["_boundary_geometry"],
        crs=rooms.crs,
    )

    joined = gpd.sjoin(
        combined_doors[[config.entity_col, "door_xyxy", "geometry"]],
        boundary_gdf,
        how="left",
        predicate="intersects",
    )

    valid = joined.dropna(subset=["_room_idx"]).copy()
    valid["_room_idx"] = valid["_room_idx"].astype(int)

    attachments = (
        valid.groupby(["_room_idx", config.entity_col], sort=False)["door_xyxy"]
        .first()
        .reset_index()
    )

    doors_by_room = (
        attachments.groupby("_room_idx", sort=False)["door_xyxy"]
        .apply(list)
        .rename(config.out_col)
    )

    attachment_counts = (
        valid.groupby(config.entity_col)["_room_idx"]
        .nunique()
        .rename("attached_room_count")
    )

    unresolved_doors = (
        combined_doors[[config.entity_col]]
        .merge(
            attachment_counts,
            left_on=config.entity_col,
            right_index=True,
            how="left",
        )
        .fillna({"attached_room_count": 0})
    )

    unresolved_doors["door_attachment_warning"] = (
        unresolved_doors["attached_room_count"].astype(int) > config.max_attached_rooms
    ) | (unresolved_doors["attached_room_count"].astype(int) == 0)

    result = labelled_polygons.copy()
    result = result.join(doors_by_room, how="left")
    result[config.out_col] = result[config.out_col].apply(
        lambda v: v if isinstance(v, list) else []
    )

    result["door_count"] = result[config.out_col].apply(len)

    result.attrs.update(source_attrs)
    result.attrs["door_attachment_report"] = unresolved_doors.to_dict(orient="records")

    return result


def _flatten_z_points(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Remove Z-coordinates from point geometries in a GeoDataFrame.

    Any geometry that is a Shapely Point with a Z dimension is converted
    to a 2D Point using its X and Y coordinates. All other geometries are
    returned unchanged.

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        Input GeoDataFrame containing point geometries.

    Returns
    -------
    geopandas.GeoDataFrame
        A copy of the input GeoDataFrame with Z-coordinates removed
        from point geometries where applicable.

    """
    g = gdf.copy()

    g["geometry"] = shapely.force_2d(g.geometry)

    return g


def _repair_polygon_geometry(geom: BaseGeometry) -> BaseGeometry:
    geom = shapely.force_2d(geom)

    if geom.is_empty:
        return geom

    if not geom.is_valid:
        geom = shapely.make_valid(geom)

    if geom.geom_type == "MultiPolygon":
        return max(geom.geoms, key=lambda g: g.area)

    return geom


def _generate_polygons(
    gdf: gpd.GeoDataFrame,
    polygon_layer_name: str,
) -> gpd.GeoDataFrame:
    """
    Generate polygon geometries from linework in a specified DXF layer.

    The function filters the input GeoDataFrame by layer name and applies
    Shapely's polygonize operation to convert line geometries into polygons.

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        Input GeoDataFrame containing DXF-derived geometries.
    polygon_layer_name : str
        Name of the DXF layer containing polygon boundary linework.

    Returns
    -------
    geopandas.GeoDataFrame
        A GeoDataFrame containing polygon geometries derived from the
        specified layer.

    """
    polygon_layer = gdf.loc[gdf["Layer"] == polygon_layer_name, ["geometry"]].copy()
    polygon_layer["geometry"] = shapely.force_2d(polygon_layer.geometry)

    polygon_layer = polygon_layer.loc[
        polygon_layer.geometry.geom_type.isin(
            {"LineString", "MultiLineString", "LinearRing"}
        ),
        :,
    ]

    raw_polygons = list(polygonize(polygon_layer.geometry))
    repaired = [_repair_polygon_geometry(geom) for geom in raw_polygons]

    polygons = gpd.GeoDataFrame(geometry=repaired, crs=gdf.crs)
    polygons = polygons.loc[
        polygons.geometry.geom_type == "Polygon",
        :,
    ]
    polygons = polygons.loc[~polygons.geometry.is_empty, :]
    polygons = polygons.loc[polygons.geometry.area > 0, :]

    return polygons.reset_index(drop=True)


def _apply_polygon_splits(
    polygons: gpd.GeoDataFrame,
    split_configs: list[PolygonSplitConfig],
) -> gpd.GeoDataFrame:
    """Split configured polygons using explicit floorplan cut lines."""
    result = polygons.copy()

    for split_config in split_configs:
        selector = Point(split_config.selector_point)
        matching_indices = result.index[result.geometry.covers(selector)]
        if len(matching_indices) != 1:
            msg = (
                "Polygon split selector must identify exactly one polygon; "
                f"found {len(matching_indices)}"
            )
            raise ValueError(msg)

        source_index = matching_indices[0]
        pieces: list[BaseGeometry] = [result.loc[source_index, "geometry"]]
        for cut_line in split_config.cut_lines:
            cutter = LineString(
                [(cut_line[0], cut_line[1]), (cut_line[2], cut_line[3])]
            )
            pieces = [
                part
                for piece in pieces
                for part in split(piece, cutter).geoms
                if part.geom_type == "Polygon" and not part.is_empty
            ]

        if len(pieces) < 2:
            msg = "Configured cut lines did not split the selected polygon"
            raise ValueError(msg)

        result = result.drop(index=source_index)
        result = gpd.GeoDataFrame(
            pd.concat(
                [
                    result,
                    gpd.GeoDataFrame(geometry=pieces, crs=result.crs),
                ],
                ignore_index=True,
            ),
            geometry="geometry",
            crs=result.crs,
        )

    return result.reset_index(drop=True)


def _apply_polygon_additions(
    polygons: gpd.GeoDataFrame,
    addition_configs: list[PolygonAdditionConfig],
) -> gpd.GeoDataFrame:
    """Add explicitly configured polygons absent from source linework."""
    additions = [Polygon(addition.coordinates) for addition in addition_configs]
    if not additions:
        return polygons
    if not all(polygon.is_valid and polygon.area > 0 for polygon in additions):
        msg = "Configured polygon additions must be valid positive-area polygons"
        raise ValueError(msg)

    return gpd.GeoDataFrame(
        pd.concat(
            [
                polygons,
                gpd.GeoDataFrame(geometry=additions, crs=polygons.crs),
            ],
            ignore_index=True,
        ),
        geometry="geometry",
        crs=polygons.crs,
    )


def _apply_split_region_labels(
    polygons: gpd.GeoDataFrame,
    split_configs: list[PolygonSplitConfig],
    polygon_label_target: str,
) -> gpd.GeoDataFrame:
    """Apply explicit labels to regions created by configured polygon splits."""
    result = polygons.copy()

    for split_config in split_configs:
        for region in split_config.regions:
            seed = Point(region.seed_point)
            matching_indices = result.index[result.geometry.covers(seed)]
            if len(matching_indices) != 1:
                msg = (
                    "Split region seed must identify exactly one polygon; "
                    f"found {len(matching_indices)}"
                )
                raise ValueError(msg)

            region_index = matching_indices[0]
            result.loc[
                region_index,
                [polygon_label_target, "label_count", "label_ambiguous"],
            ] = [region.label, 1, False]
            result.loc[[region_index], "label_candidates"] = pd.Series(
                [[region.label]],
                index=[region_index],
            )

    return result


def _apply_addition_labels(
    polygons: gpd.GeoDataFrame,
    addition_configs: list[PolygonAdditionConfig],
    polygon_label_target: str,
) -> gpd.GeoDataFrame:
    """Apply labels to explicitly configured polygon additions."""
    result = polygons.copy()
    addition_count = len(addition_configs)
    if addition_count == 0:
        return result

    addition_indices = result.index[-addition_count:]
    for addition_index, addition in zip(
        addition_indices,
        addition_configs,
        strict=True,
    ):
        result.loc[
            addition_index,
            [polygon_label_target, "label_count", "label_ambiguous"],
        ] = [addition.label, 1, False]
        result.loc[[addition_index], "label_candidates"] = pd.Series(
            [[addition.label]],
            index=[addition_index],
        )

    return result


def _apply_polygon_merges(
    polygons: gpd.GeoDataFrame,
    merge_configs: list[PolygonMergeConfig],
    polygon_label_target: str,
) -> gpd.GeoDataFrame:
    """Merge configured source polygons into a single labelled target polygon."""
    result = polygons.copy()

    for merge_config in merge_configs:
        target_indices = result.index[
            result[polygon_label_target] == merge_config.target_label
        ]
        if len(target_indices) != 1:
            msg = (
                "Polygon merge target must identify exactly one polygon; "
                f"label {merge_config.target_label!r} found {len(target_indices)}"
            )
            raise ValueError(msg)

        source_indices: list[int] = []
        for source_label in merge_config.source_labels:
            matching_indices = result.index[
                result[polygon_label_target] == source_label
            ].to_list()
            if not matching_indices:
                msg = (
                    "Polygon merge source must identify at least one polygon; "
                    f"label {source_label!r} found 0"
                )
                raise ValueError(msg)
            source_indices.extend(matching_indices)

        target_index = target_indices[0]
        merged_geometry = unary_union(
            result.loc[[target_index, *source_indices], "geometry"].to_list()
        )
        if (
            not isinstance(merged_geometry, Polygon)
            or merged_geometry.is_empty
            or not merged_geometry.is_valid
        ):
            msg = (
                "Polygon merge must produce one valid Polygon; "
                f"got {merged_geometry.geom_type}"
            )
            raise ValueError(msg)

        result.loc[target_index, "geometry"] = merged_geometry
        result.loc[
            target_index,
            [polygon_label_target, "label_count", "label_ambiguous"],
        ] = [merge_config.target_label, 1, False]
        result.loc[[target_index], "label_candidates"] = pd.Series(
            [[merge_config.target_label]],
            index=[target_index],
        )
        result = result.drop(index=source_indices)

    return result.reset_index(drop=True)


def _generate_room_numbers(
    gdf: gpd.GeoDataFrame,
    label_layer_name: str,
    floor_filter: str,
    polygon_label_column: str,
    excluded_room_numbers: list[str],
) -> gpd.GeoDataFrame:
    """
    Extract and filter room label point geometries for a given floor.

    Room labels are selected from a specific DXF layer. Multiline text is
    normalised to the line beginning with the configured floor prefix before
    exclusions are applied. Any Z-coordinates present on point geometries are
    removed.

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        Input GeoDataFrame containing DXF-derived geometries.
    label_layer_name : str
        Name of the DXF layer containing room label points.
    floor_filter : str
        Prefix used to select labels belonging to a specific floor.
    polygon_label_column : str
        Name of the column containing room label text.
    excluded_room_numbers : list[str]
        List of room numbers to be excluded.

    Returns
    -------
    geopandas.GeoDataFrame
        A GeoDataFrame containing filtered 2D room label point geometries.

    """
    room_number_layer = gdf.loc[
        gdf["Layer"] == label_layer_name,
        [polygon_label_column, "geometry"],
    ].copy()
    room_number_layer[polygon_label_column] = room_number_layer[
        polygon_label_column
    ].apply(lambda value: _extract_floor_label(value, floor_filter))
    room_numbers = room_number_layer.loc[
        room_number_layer[polygon_label_column].notna()
        & ~room_number_layer[polygon_label_column].isin(excluded_room_numbers),
        [polygon_label_column, "geometry"],
    ]

    return _flatten_z_points(room_numbers)


def _extract_floor_label(value: object, floor_filter: str) -> str | None:
    """Return the first trimmed label line matching the floor prefix."""
    if not isinstance(value, str):
        return None

    return next(
        (
            line.strip()
            for line in value.splitlines()
            if line.strip().startswith(floor_filter)
        ),
        None,
    )


def _generate_doors(gdf: gpd.GeoDataFrame, target_layer: str) -> gpd.GeoDataFrame:
    """
    Extract door boundary geometries from a DXF GeoDataFrame.

    Door geometries are selected from a specified DXF layer, unpacked from
    GeometryCollections where necessary, exploded into individual geometries,
    converted back into a valid GeoDataFrame, forced to 2D, and annotated with
    centroid coordinates.

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        Input GeoDataFrame containing DXF-derived geometries.
    target_layer : str
        Name of the DXF layer containing door geometries.

    Returns
    -------
    geopandas.GeoDataFrame
        GeoDataFrame containing door boundary geometries and centroid coordinate
        columns ``x`` and ``y``.

    """
    doors = gdf.loc[
        gdf["Layer"] == target_layer,
        ["EntityHandle", "geometry"],
    ].copy()

    doors = pd.DataFrame(doors)

    doors["geometry"] = doors["geometry"].apply(_unpack_geometry)

    doors = doors.explode("geometry")

    doors = gpd.GeoDataFrame(doors, geometry="geometry")

    doors = doors.loc[
        doors.geometry.geom_type.isin({"LineString", "MultiLineString"}), :
    ]

    doors = _flatten_z_points(doors)
    return _attach_centroid_coords(doors)


def _attach_centroid_coords(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = gdf.copy()
    g["x"] = g.geometry.centroid.x
    g["y"] = g.geometry.centroid.y

    return g


def _normalise_label(value: str) -> str:
    return str(value).strip()


def _score_label(label: str) -> tuple[int, int, str]:
    clean = _normalise_label(label)
    if clean.lower() in {"corridor", "lobby", "stair", "stairs"}:
        return (1, len(clean), clean)

    has_digit = any(char.isdigit() for char in clean)
    if has_digit:
        return (0, len(clean), clean)

    return (2, len(clean), clean)


def _choose_primary_label(labels: pd.Series) -> str | None:
    values = sorted({_normalise_label(v) for v in labels if pd.notna(v)})

    if not values:
        return None

    return sorted(values, key=_score_label)[0]


def _attach_polygon_labels(
    polygons: gpd.GeoDataFrame,
    room_labels: gpd.GeoDataFrame,
    polygon_label_column: str,
    polygon_label_target: str,
) -> gpd.GeoDataFrame:
    """
    Attach room labels to polygons using a spatial point-in-polygon join.

    Room label points are spatially joined to polygons using a
    point-within-polygon predicate. All labels falling within the same
    polygon are aggregated into a single, sorted, comma-separated string.

    Parameters
    ----------
    polygons : geopandas.GeoDataFrame
        GeoDataFrame containing polygon geometries.
    room_labels : geopandas.GeoDataFrame
        GeoDataFrame containing room label point geometries.
    polygon_label_column : str
        Column containing the label text in the room label GeoDataFrame.
    polygon_label_target : str
        Name of the output column to store aggregated polygon labels.

    Returns
    -------
    geopandas.GeoDataFrame
        The polygon GeoDataFrame with aggregated label data attached
        and a geometry type indicator column.

    """
    matches = gpd.sjoin(
        room_labels,
        polygons,
        how="left",
        predicate="within",
    ).rename(columns={"index_right": "room_idx"})

    grouped = matches.dropna(subset=["room_idx"]).copy()
    grouped["room_idx"] = grouped["room_idx"].astype(int)

    label_summary = grouped.groupby("room_idx")[polygon_label_column].agg(
        primary_label=_choose_primary_label,
        label_candidates=lambda x: sorted(
            {_normalise_label(v) for v in x if pd.notna(v)}
        ),
        label_count=lambda x: len({_normalise_label(v) for v in x if pd.notna(v)}),
    )

    label_summary = label_summary.rename(
        columns={"primary_label": polygon_label_target}
    )
    label_summary["label_ambiguous"] = label_summary["label_count"] > 1

    labelled_polygons = polygons.join(label_summary, how="left")
    labelled_polygons["geometry_type"] = "POLYGON"
    labelled_polygons["label_candidates"] = labelled_polygons["label_candidates"].apply(
        lambda v: v if isinstance(v, list) else []
    )
    labelled_polygons["label_count"] = (
        labelled_polygons["label_count"].fillna(0).astype(int)
    )
    labelled_polygons["label_ambiguous"] = labelled_polygons["label_ambiguous"].fillna(
        value=False
    )

    return labelled_polygons


def _unpack_geometry(geom: BaseGeometry) -> list[BaseGeometry]:
    """
    Unpack a Shapely geometry into its component geometries.

    Parameters
    ----------
    geom : shapely.geometry.base.BaseGeometry
        Input geometry. May be a ``GeometryCollection`` or any other Shapely
        geometry type.

    Returns
    -------
    list[BaseGeometry]
        If ``geom`` is a ``GeometryCollection``, returns a list of its member
        geometries. Otherwise, returns a single-element list containing
        ``geom`` itself.

    Notes
    -----
    This function normalises geometry handling by ensuring downstream code
    can iterate over a list of geometries regardless of the original type.

    """
    if isinstance(geom, GeometryCollection):
        return list(geom.geoms)

    return [geom]


def extract_polygons(
    input_dxf_path: Path,
    config: ExtractionConfig,
) -> gpd.GeoDataFrame:
    """
    Extract labelled polygons from a DXF floorplan.

    The DXF file is read into a GeoDataFrame, polygon geometries are
    generated from linework, room label points are filtered by floor,
    and labels are spatially joined to the resulting polygons.

    Parameters
    ----------
    input_dxf_path : pathlib.Path
        Path to the input DXF file.
    config : ExtractionConfig
        Configuration object controlling layer names, label filtering, and output column
        names.

    Returns
    -------
    geopandas.GeoDataFrame
        A GeoDataFrame containing labelled polygon geometries.

    """
    gdf = gpd.read_file(input_dxf_path)

    polygons = _generate_polygons(gdf, config.polygons.polygon_layer_name)
    polygons = _apply_polygon_splits(polygons, config.polygon_splits)
    polygons = _apply_polygon_additions(polygons, config.polygon_additions)

    room_numbers = _generate_room_numbers(
        gdf,
        config.polygons.label_layer_name,
        config.polygons.floor_filter,
        config.polygons.polygon_label_column,
        config.polygons.excluded_room_numbers,
    )

    labelled_polygons = _attach_polygon_labels(
        polygons,
        room_numbers,
        config.polygons.polygon_label_column,
        config.polygons.polygon_label_target,
    )
    labelled_polygons = _apply_split_region_labels(
        labelled_polygons,
        config.polygon_splits,
        config.polygons.polygon_label_target,
    )
    labelled_polygons = _apply_addition_labels(
        labelled_polygons,
        config.polygon_additions,
        config.polygons.polygon_label_target,
    )
    labelled_polygons = _apply_polygon_merges(
        labelled_polygons,
        config.polygon_merges,
        config.polygons.polygon_label_target,
    )

    if config.shared_walls and config.shared_walls.enabled:
        labelled_polygons = normalise_shared_walls(
            labelled_polygons,
            config.shared_walls,
        )

    if config.door_layer_name and config.doors:
        doors = _generate_doors(gdf, config.door_layer_name)
        labelled_polygons = attach_room_doors(
            labelled_polygons,
            doors,
            config.doors,
        )

    labelled_polygons["has_label"] = labelled_polygons[
        config.polygons.polygon_label_target
    ].notna()

    labelled_polygons["needs_review"] = (
        ~labelled_polygons["has_label"]
        | labelled_polygons.get("label_ambiguous", False)
        | (labelled_polygons.get("door_count", 0) == 0)
        | labelled_polygons.get("shared_wall_review", False)
    )

    return labelled_polygons
