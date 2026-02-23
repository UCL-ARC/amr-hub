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

import geopandas as gpd
import shapely
from shapely.geometry import Point
from shapely.ops import polygonize


@dataclass(frozen=True)
class PolygonExtractionConfig:
    """
    Configuration for DXF polygon extraction and labelling.

    This dataclass groups all non-file parameters required to extract
    polygon geometries from DXF linework and attach room labels. It is
    intended to be passed as a single, immutable configuration object
    to the extraction pipeline.

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

    """

    polygon_layer_name: str
    label_layer_name: str
    polygon_label_column: str
    polygon_label_target: str
    floor_filter: str


def config_from_yaml(path: Path) -> PolygonExtractionConfig:
    """
    Load polygon extraction configuration from a YAML file.

    The YAML file must define keys corresponding exactly to the fields
    of `PolygonExtractionConfig`.

    Parameters
    ----------
    path : pathlib.Path
        Path to the YAML configuration file.

    Returns
    -------
    PolygonExtractionConfig
        An immutable configuration instance populated from the file.

    """
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return PolygonExtractionConfig(**data)


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

    g["geometry"] = g.geometry.apply(
        lambda geom: (
            Point(geom.x, geom.y) if isinstance(geom, Point) and geom.has_z else geom
        )
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
    room_numbers = room_number_layer.loc[
        room_number_layer[polygon_label_column].str.startswith(floor_filter),
        [polygon_label_column, "geometry"],
    ]

    return _flatten_z_points(room_numbers)


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
    ].apply(lambda x: ", ".join(sorted(x)))

    labelled_polygons = polygons.join(aggregated_labels)
    labelled_polygons = labelled_polygons.rename(
        columns={polygon_label_column: polygon_label_target}
    )
    labelled_polygons["geometry_type"] = "POLYGON"

    return labelled_polygons


def extract_polygons(
    input_dxf_path: Path,
    config: PolygonExtractionConfig,
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

    polygons = _generate_polygons(gdf, config.polygon_layer_name)

    room_numbers = _generate_room_numbers(
        gdf,
        config.label_layer_name,
        config.floor_filter,
        config.polygon_label_column,
    )

    return _attach_polygon_labels(
        polygons,
        room_numbers,
        config.polygon_label_column,
        config.polygon_label_target,
    )
