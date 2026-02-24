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
from typing import TYPE_CHECKING, Any, cast

import geopandas as gpd
import shapely
import yaml
from shapely.geometry import GeometryCollection
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize

if TYPE_CHECKING:
    import pandas as pd


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

    required_doors_cols = {
        config.entity_col,
        config.x_col,
        config.y_col,
        "geometry",
    }
    missing = required_doors_cols.difference(doors.columns)
    if missing:
        msg = f"doors is missing required columns: {sorted(missing)}"
        raise KeyError(msg)

    if "geometry" not in labelled_polygons.columns:
        msg = "labelled_polygons must have a 'geometry' column"
        raise KeyError(msg)

    joined = gpd.sjoin(
        doors[[config.entity_col, config.x_col, config.y_col, "geometry"]],
        labelled_polygons[["geometry"]],
        how="inner",
        predicate=config.predicate,
    ).rename(columns={"index_right": "room_idx"})

    points = joined.groupby(["room_idx", config.entity_col], sort=False)[
        [config.x_col, config.y_col]
    ].apply(
        lambda df: list(
            zip(
                df[config.x_col].astype(float),
                df[config.y_col].astype(float),
                strict=True,
            )
        )
    )

    quads = points.apply(_pair_points_to_quad).dropna().rename("door_xyxy")

    doors_by_room = (
        cast("pd.Series", quads)
        .groupby(level=0, sort=False)
        .apply(list)
        .rename(config.out_col)
    )

    result = labelled_polygons.copy()
    result = result.join(doors_by_room, how="left")
    result[config.out_col] = result[config.out_col].apply(
        lambda v: v if isinstance(v, list) else []
    )
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
    excluded_room_numbers: list[str] | None = None,
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
    doors = gdf.loc[gdf["Layer"] == target_layer, :]
    doors = doors.loc[
        doors.geometry.geom_type == "GeometryCollection", ["EntityHandle", "geometry"]
    ]

    doors["geometry"] = doors["geometry"].apply(_unpack_geometry)
    doors = doors.explode("geometry", index_parts=False)
    doors = gpd.GeoDataFrame(doors, geometry="geometry")

    door_bounds = doors.loc[doors.geometry.geom_type == "MultiLineString", :]
    door_bounds = _flatten_z_points(door_bounds)
    return _attach_centroid_coords(door_bounds)


def _attach_centroid_coords(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = gdf.copy()
    g["x"] = g.geometry.centroid.x
    g["y"] = g.geometry.centroid.y

    return g


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
    number_polygon_matches = gpd.sjoin(
        room_labels, polygons, how="left", predicate="within"
    )

    aggregated_labels = number_polygon_matches.groupby("index_right")[
        polygon_label_column
    ].apply(lambda x: ", ".join(sorted(set(x))))

    labelled_polygons = polygons.join(aggregated_labels)
    labelled_polygons = labelled_polygons.rename(
        columns={polygon_label_column: polygon_label_target}
    )
    labelled_polygons["geometry_type"] = "POLYGON"

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
    polygon_layer_name : str
        Name of the DXF layer containing polygon boundary linework.
    label_layer_name : str
        Name of the DXF layer containing room label points.
    polygon_label_column : str
        Column containing room label text.
    polygon_label_target : str
        Name of the output column for polygon labels.
    floor_filter : str
        Prefix used to select labels for a specific floor.

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

    complete_polygons = labelled_polygons
    if config.door_layer_name and config.doors:
        doors = _generate_doors(gdf, config.door_layer_name)
        labelled_polygons = attach_room_doors(
            labelled_polygons,
            doors,
            config.doors,
        )

    return complete_polygons.loc[
        complete_polygons[config.polygons.polygon_label_target].notna(), :
    ]
