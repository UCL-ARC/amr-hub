"""
YAML serialisation of indoor building geometry.

This module provides utilities for converting labelled room polygons into
a structured, human-readable YAML representation of a building floorplan.
It operates on GeoDataFrame-derived polygon geometries and produces a schema
focused on architectural topology rather than geospatial metadata.

Responsibilities of this module include:
- Converting polygon exteriors into ordered wall segments.
- Mapping labelled polygons to room definitions.
- Assembling building- and floor-level metadata into a serialisable form.
- Writing the resulting structure to disk as YAML.

The module assumes:
- One polygon corresponds to one room.
- Polygon geometries are valid, closed, and planar.
- Coordinates exist in a local Cartesian space with no CRS.
- Room labels have already been attached upstream.

DXF parsing, spatial joins, and geometry construction are explicitly out of
scope and must be handled before using this module.
"""

from itertools import pairwise

import geopandas as gpd
import yaml
from shapely.geometry import Polygon
from yaml.nodes import SequenceNode
from yaml.representer import SafeRepresenter


class FlowList(list):
    """List subtype used to force YAML flow-style serialisation."""


def _represent_flow_list(
    dumper: SafeRepresenter,
    data: FlowList,
) -> SequenceNode:
    """
    Represent a FlowList as a YAML flow-style sequence.

    This representer forces lists of wall coordinates to be emitted in
    flow style (e.g. `[x1, y1, x2, y2]`) when using `yaml.safe_dump`.
    """
    return dumper.represent_sequence(
        "tag:yaml.org,2002:seq",
        data,
        flow_style=True,
    )


def register_yaml_representers() -> None:
    """
    Register custom YAML representers used by the building serialisation module.

    This function registers a representer for the `FlowList` type with
    PyYAML's `SafeDumper`, ensuring that wall segment coordinate lists are
    emitted in flow style (e.g. `[x1, y1, x2, y2]`) when using
    `yaml.safe_dump`.

    The registration mutates PyYAML's global dumper state and therefore
    must be called exactly once, before any YAML serialisation occurs.
    It is intentionally explicit to avoid hidden import-time side effects.

    Returns
    -------
    None

    """
    yaml.SafeDumper.add_representer(FlowList, _represent_flow_list)


def _polygon_to_walls(polygon: Polygon) -> list[list[float]]:
    """
    Convert a polygon exterior into ordered wall segments.

    Parameters
    ----------
    polygon : shapely.geometry.Polygon
        Polygon representing a room footprint.

    Returns
    -------
    list[list[float]]
        Wall segments as [x1, y1, x2, y2].

    """
    if not isinstance(polygon, Polygon):
        return []

    if polygon.is_empty or not polygon.is_valid:
        return []

    coords = list(polygon.exterior.coords)

    return [FlowList([x1, y1, x2, y2]) for (x1, y1), (x2, y2) in pairwise(coords)]


def polygons_to_rooms(
    gdf: gpd.GeoDataFrame,
    room_name_column: str,
) -> list[dict]:
    """
    Convert labelled polygons into room definitions.

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        GeoDataFrame containing polygon geometries.
    room_name_column : str
        Column containing room names.

    Returns
    -------
    list[dict]
        Room definitions suitable for YAML serialisation.

    """
    rooms = []

    for _, row in gdf.iterrows():
        d = {
            "name": row[room_name_column],
            "walls": _polygon_to_walls(row.geometry),
            "doors": [],  # placeholder
        }
        rooms.append(d)

    return rooms


def build_yaml_structure(
    *,
    building_name: str,
    building_address: str,
    floor_level: int,
    rooms: list[dict],
) -> dict:
    """
    Construct a YAML-ready building data structure from room definitions.

    This function assembles building metadata and a collection of room
    definitions into a nested dictionary matching the expected output
    schema. The resulting structure is suitable for serialisation using
    `yaml.safe_dump` without further transformation.

    The function does not perform validation of room geometry or schema
    completeness. It assumes that each room dictionary contains, at a
    minimum, the keys:
        - "name"
        - "walls"
        - "doors"

    Parameters
    ----------
    building_name : str
        Name of the building.
    building_address : str
        Address of the building.
    floor_level : int
        Floor identifier to associate with the provided rooms.
    rooms : list[dict]
        List of room definitions produced by `polygons_to_rooms`.

    Returns
    -------
    dict
        Nested dictionary structured as:

        {
            "building": {
                "name": str,
                "address": str,
                "floors": [
                    {
                        "level": int,
                        "rooms": list[dict],
                    }
                ],
            }
        }

    """
    return {
        "building": {
            "name": building_name,
            "address": building_address,
            "floors": [
                {
                    "level": floor_level,
                    "rooms": rooms,
                }
            ],
        }
    }
