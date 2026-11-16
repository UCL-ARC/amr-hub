"""
YAML serialisation of indoor building geometry.

This module provides utilities for converting labelled room polygons into
a structured, human-readable YAML representation of a building floorplan.
It operates on GeoDataFrame-derived polygon geometries and produces a schema
focused on architectural topology rather than geospatial metadata.

Responsibilities of this module include:
- Converting polygon exteriors into ordered wall segments.
- Mapping labelled polygons and canonical door segments to room definitions.
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
from math import isfinite
from typing import Literal

import geopandas as gpd
import yaml
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from yaml.nodes import SequenceNode
from yaml.representer import SafeRepresenter

from amr_hub_abm.exceptions import InvalidDefinitionError, InvalidDoorError
from amr_hub_abm.spatial.units import SPATIAL_SCHEMA_VERSION, CoordinateUnit
from floorplan_extractor.spatial_units import SpatialUnits


class FlowList(list):
    """List subtype used to force YAML flow-style serialisation."""


def _segment_key(segment: list[float]) -> tuple[tuple[float, float], ...]:
    """Return an orientation-independent key for a line segment."""
    if len(segment) != 4:
        msg = f"Door segments must contain four coordinates. Got {segment}."
        raise InvalidDoorError(msg)
    start = (float(segment[0]), float(segment[1]))
    end = (float(segment[2]), float(segment[3]))
    return tuple(sorted((start, end)))


def apply_door_cardinality_policy(
    rooms: list[dict],
    *,
    singleton_policy: Literal["error", "wall"] = "error",
) -> list[dict]:
    """
    Validate door attachments and handle doors connected to only one room.

    The runtime requires each model door to connect exactly two rooms. A
    singleton segment can instead be restored to the physical wall geometry
    when the model intentionally treats the outside as impassable.

    Parameters
    ----------
    rooms : list[dict]
        Room definitions containing ``walls`` and ``doors`` segment lists.
    singleton_policy : {"error", "wall"}, default="error"
        Whether a door attached to one room raises an error or is restored as a
        physical wall segment.

    Returns
    -------
    list[dict]
        Copied room definitions with the selected policy applied.

    Raises
    ------
    InvalidDefinitionError
        If ``singleton_policy`` is unsupported.
    InvalidDoorError
        If a door does not connect exactly two rooms and the selected policy
        cannot resolve it.

    """
    if singleton_policy not in {"error", "wall"}:
        msg = f"Unsupported singleton door policy: {singleton_policy}"
        raise InvalidDefinitionError(msg)

    copied_rooms = [
        {
            **room,
            "walls": [FlowList(wall) for wall in room.get("walls", [])],
            "doors": [FlowList(door) for door in room.get("doors", [])],
        }
        for room in rooms
    ]
    attachments: dict[tuple[tuple[float, float], ...], set[int]] = {}
    for room_index, room in enumerate(copied_rooms):
        for door in room["doors"]:
            attachments.setdefault(_segment_key(door), set()).add(room_index)

    over_connected = {
        segment: room_indexes
        for segment, room_indexes in attachments.items()
        if len(room_indexes) > 2
    }
    if over_connected:
        segment, room_indexes = next(iter(over_connected.items()))
        msg = f"Door segment {segment} is attached to {len(room_indexes)} rooms"
        raise InvalidDoorError(msg)

    singleton_segments = {
        segment
        for segment, room_indexes in attachments.items()
        if len(room_indexes) == 1
    }
    if singleton_segments and singleton_policy == "error":
        segment = next(iter(singleton_segments))
        room_index = next(iter(attachments[segment]))
        room_name = copied_rooms[room_index]["name"]
        msg = f"Door segment {segment} is attached only to room '{room_name}'"
        raise InvalidDoorError(msg)

    if singleton_policy == "wall":
        for room in copied_rooms:
            retained_doors = []
            wall_segments = {_segment_key(wall) for wall in room["walls"]}
            for door in room["doors"]:
                segment = _segment_key(door)
                if segment not in singleton_segments:
                    retained_doors.append(door)
                    continue
                if segment not in wall_segments:
                    room["walls"].append(FlowList(door))
                    wall_segments.add(segment)
            room["doors"] = retained_doors

    return copied_rooms


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


def _line_to_flow_lists(geometry: BaseGeometry) -> list[FlowList]:
    """Convert linear geometry components to ordered YAML line segments."""
    if geometry.is_empty:
        return []

    if isinstance(geometry, LineString):
        lines = [geometry]
    elif geometry.geom_type == "MultiLineString":
        lines = list(geometry.geoms)
    else:
        return []

    lines.sort(key=lambda line: tuple(line.coords[0]))
    return [
        FlowList(
            [
                float(line.coords[0][0]),
                float(line.coords[0][1]),
                float(line.coords[-1][0]),
                float(line.coords[-1][1]),
            ]
        )
        for line in lines
    ]


def _polygon_to_walls(
    polygon: Polygon,
    openings: list[LineString] | None = None,
    opening_tolerance: float = 1.0e-6,
) -> list[list[float]]:
    """
    Convert a polygon exterior into ordered wall segments.

    Parameters
    ----------
    polygon : shapely.geometry.Polygon
        Polygon representing a room footprint.
    openings : list[shapely.geometry.LineString] or None, optional
        Opening centrelines to remove from the physical wall segments.
    opening_tolerance : float, default 1e-6
        Maximum distance between an opening and a polygon boundary for the
        opening to be removed from that boundary.

    Returns
    -------
    list[list[float]]
        Wall segments as [x1, y1, x2, y2].

    """
    if not isinstance(polygon, Polygon):
        return []

    if polygon.is_empty or not polygon.is_valid:
        return []
    if not isfinite(opening_tolerance) or opening_tolerance < 0.0:
        msg = "opening_tolerance must be finite and non-negative"
        raise ValueError(msg)

    coords = list(polygon.exterior.coords)
    walls: list[list[float]] = []
    for (x1, y1), (x2, y2) in pairwise(coords):
        segment: BaseGeometry = LineString([(x1, y1), (x2, y2)])
        segment_openings = [
            LineString(
                [
                    segment.interpolate(segment.project(Point(opening.coords[0]))),
                    segment.interpolate(segment.project(Point(opening.coords[-1]))),
                ]
            )
            for opening in openings or []
            if segment.distance(opening) <= opening_tolerance
        ]
        if segment_openings:
            segment = segment.difference(unary_union(segment_openings))
        walls.extend(_line_to_flow_lists(segment))

    return walls


def polygons_to_rooms(
    gdf: gpd.GeoDataFrame,
    room_name_column: str,
    door_column: str | None = None,
    opening_column: str | None = None,
    opening_tolerance: float = 1.0e-6,
) -> list[dict]:
    """
    Convert labelled polygons into room definitions.

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        GeoDataFrame containing polygon geometries.
    room_name_column : str
        Column containing room names.
    door_column : str or None
        Optional column containing lists of canonical door segments represented
        as ``[x1, y1, x2, y2]``. These spans are emitted as doors and removed
        from the physical wall list.
    opening_column : str or None
        Optional column containing lists of non-operable opening segments. When
        provided, those segments are emitted as ``openings`` and removed from
        the room's physical wall list.
    opening_tolerance : float, default 1e-6
        Maximum boundary distance accepted when removing an opening from the
        physical wall list.

    Returns
    -------
    list[dict]
        Room definitions containing ``name``, ``walls``, and ``doors`` values
        suitable for YAML serialisation.

    """
    rooms = []

    for _, row in gdf.iterrows():
        door_values = []
        if door_column and door_column in row and row[door_column]:
            door_values = [FlowList(d) for d in row[door_column]]

        opening_values = []
        if opening_column and opening_column in row and row[opening_column]:
            opening_values = [FlowList(opening) for opening in row[opening_column]]
        opening_lines = [
            LineString([(opening[0], opening[1]), (opening[2], opening[3])])
            for opening in opening_values
        ]
        door_lines = [
            LineString([(door[0], door[1]), (door[2], door[3])]) for door in door_values
        ]

        d = {
            "name": row[room_name_column],
            "walls": _polygon_to_walls(
                row.geometry,
                [*opening_lines, *door_lines],
                opening_tolerance=opening_tolerance,
            ),
            "doors": door_values,
        }
        if opening_column is not None:
            d["openings"] = opening_values
        rooms.append(d)

    return rooms


def build_yaml_structure(
    *,
    building_name: str,
    building_address: str,
    floor_level: int,
    rooms: list[dict],
    spatial_units: SpatialUnits,
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
    spatial_units : floorplan_extractor.spatial_units.SpatialUnits
        Explicit conversion from source coordinates to canonical metres.

    Returns
    -------
    dict
        Nested dictionary structured as:

        {
            "schema_version": 1,
            "coordinate_unit": "m",
            "coordinate_provenance": {
                "source_unit": str,
                "units_per_metre": float,
            },
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
    canonical_rooms = [_room_to_canonical_metres(room, spatial_units) for room in rooms]
    return {
        "schema_version": SPATIAL_SCHEMA_VERSION,
        "coordinate_unit": CoordinateUnit.METRE.value,
        "coordinate_provenance": {
            "source_unit": spatial_units.source_unit,
            "units_per_metre": spatial_units.units_per_metre,
        },
        "building": {
            "name": building_name,
            "address": building_address,
            "floors": [
                {
                    "level": floor_level,
                    "rooms": canonical_rooms,
                }
            ],
        },
    }


def _room_to_canonical_metres(
    room: dict,
    spatial_units: SpatialUnits,
) -> dict:
    """Copy one room definition and convert all known spatial values to SI units."""
    converted = dict(room)
    for field_name in ("walls", "doors", "openings"):
        values = room.get(field_name)
        if isinstance(values, list) and all(
            isinstance(value, list) for value in values
        ):
            converted[field_name] = [
                FlowList(spatial_units.to_metres(coordinate) for coordinate in value)
                for value in values
            ]

    contents = room.get("contents")
    if isinstance(contents, list):
        converted_contents = []
        for content in contents:
            converted_content = dict(content)
            position = content.get("position")
            if isinstance(position, list):
                converted_content["position"] = [
                    spatial_units.to_metres(coordinate) for coordinate in position
                ]
            converted_contents.append(converted_content)
        converted["contents"] = converted_contents

    area = room.get("area")
    if isinstance(area, (int, float)) and not isinstance(area, bool):
        converted["area"] = spatial_units.area_to_square_metres(area)
    return converted
