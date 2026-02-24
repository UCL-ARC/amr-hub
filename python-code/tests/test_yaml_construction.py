"""Module for testing construction of yaml polygons."""

import geopandas as gpd
import yaml
from shapely.geometry import Polygon

from floorplan_extractor.yaml_construction import (
    FlowList,
    _polygon_to_walls,
    build_yaml_structure,
    polygons_to_rooms,
    register_yaml_representers,
)

# Constants
SQUARE_COORDINATES: list[tuple[float, float]] = [
    (0.0, 0.0),
    (1.0, 0.0),
    (1.0, 1.0),
    (0.0, 1.0),
]

EXPECTED_WALL_COUNT: int = 4
EXPECTED_FIRST_WALL: list[float] = [0.0, 0.0, 1.0, 0.0]

BUILDING_NAME: str = "Test Building"
BUILDING_ADDRESS: str = "1 Test Street"
FLOOR_LEVEL: int = 1

ROOM_NAME_COLUMN: str = "room_name"
ROOM_NAME: str = "Room A"


def test_polygon_to_walls_valid_polygon() -> None:
    """Valid square polygon produces four ordered wall segments."""
    polygon: Polygon = Polygon(SQUARE_COORDINATES)

    walls: list[list[float]] = _polygon_to_walls(polygon)

    assert len(walls) == EXPECTED_WALL_COUNT
    assert all(isinstance(w, FlowList) for w in walls)
    assert walls[0] == EXPECTED_FIRST_WALL


def test_polygon_to_walls_invalid_input() -> None:
    """Non-polygon input returns an empty list."""
    result: list[list[float]] = _polygon_to_walls(None)  # type: ignore[arg-type]

    assert result == []


def test_polygons_to_rooms_basic() -> None:
    """Single labelled polygon is converted into a room definition."""
    polygon: Polygon = Polygon(SQUARE_COORDINATES)

    gdf: gpd.GeoDataFrame = gpd.GeoDataFrame(
        {ROOM_NAME_COLUMN: [ROOM_NAME], "geometry": [polygon]},
        geometry="geometry",
    )

    rooms: list[dict] = polygons_to_rooms(
        gdf,
        ROOM_NAME_COLUMN,
        door_column=None,
    )

    assert len(rooms) == 1
    assert rooms[0]["name"] == ROOM_NAME
    assert len(rooms[0]["walls"]) == EXPECTED_WALL_COUNT
    assert rooms[0]["doors"] == []


def test_build_yaml_structure_schema() -> None:
    """Building metadata and rooms are assembled into expected schema."""
    rooms: list[dict] = [{"name": ROOM_NAME, "walls": [], "doors": []}]

    data: dict = build_yaml_structure(
        building_name=BUILDING_NAME,
        building_address=BUILDING_ADDRESS,
        floor_level=FLOOR_LEVEL,
        rooms=rooms,
    )

    assert "building" in data
    assert data["building"]["name"] == BUILDING_NAME
    assert data["building"]["floors"][0]["level"] == FLOOR_LEVEL
    assert data["building"]["floors"][0]["rooms"] == rooms


def test_yaml_flow_style_serialisation() -> None:
    """FlowList values are emitted in YAML flow style."""
    register_yaml_representers()

    walls: list[FlowList] = [FlowList(EXPECTED_FIRST_WALL)]
    dumped: str = yaml.safe_dump({"walls": walls})

    assert str(EXPECTED_FIRST_WALL) in dumped


def test_polygons_to_rooms_with_doors() -> None:
    """Room polygons with attached door geometries are serialised correctly."""
    polygon = Polygon(SQUARE_COORDINATES)

    gdf = gpd.GeoDataFrame(
        {
            ROOM_NAME_COLUMN: [ROOM_NAME],
            "doors": [[[0.0, 0.0, 1.0, 0.0]]],
            "geometry": [polygon],
        },
        geometry="geometry",
    )

    rooms = polygons_to_rooms(
        gdf,
        ROOM_NAME_COLUMN,
        door_column="doors",
    )

    assert rooms[0]["doors"] == [FlowList([0.0, 0.0, 1.0, 0.0])]
