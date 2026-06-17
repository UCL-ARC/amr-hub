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

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import shapely
import yaml
from shapely.geometry import GeometryCollection, LineString, MultiLineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, polygonize, unary_union

XY = tuple[float, float]
DoorQuad = list[float]  # [x1, y1, x2, y2]
MIN_DOOR_ENDPOINTS: int = 2


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

    """

    polygons: PolygonExtractionConfig
    door_layer_name: str | None = None
    doors: DoorAttachmentConfig | None = None


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

    return ExtractionConfig(
        polygons=polygons_cfg,
        door_layer_name=door_layer_name,
        doors=door_config,
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


def _generate_polygons(
    gdf: gpd.GeoDataFrame, polygon_layer_name: str
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
    polygon_layer = gdf.loc[gdf["Layer"] == polygon_layer_name, :]
    return gpd.GeoDataFrame(geometry=list(polygonize(polygon_layer.geometry)))


def _generate_room_numbers(
    gdf: gpd.GeoDataFrame,
    label_layer_name: str,
    floor_filter: str,
    polygon_label_column: str,
    excluded_room_numbers: list[str],
) -> gpd.GeoDataFrame:
    """
    Extract and filter room label point geometries for a given floor.

    Room labels are selected from a specific DXF layer and filtered by
    a string prefix match on the label column. Any Z-coordinates present
    on point geometries are removed.

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
    room_number_layer = gdf.loc[gdf["Layer"] == label_layer_name, :]
    room_number_layer = room_number_layer.loc[
        ~room_number_layer[polygon_label_column].isin(excluded_room_numbers), :
    ]
    room_numbers = room_number_layer.loc[
        room_number_layer[polygon_label_column].str.startswith(floor_filter),
        [polygon_label_column, "geometry"],
    ]

    return _flatten_z_points(room_numbers)


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

    if config.door_layer_name and config.doors:
        doors = _generate_doors(gdf, config.door_layer_name)
        labelled_polygons = attach_room_doors(
            labelled_polygons,
            doors,
            config.doors,
        )

    return labelled_polygons.loc[
        labelled_polygons[config.polygons.polygon_label_target].notna(), :
    ]
