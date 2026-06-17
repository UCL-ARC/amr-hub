"""Tests for shared-wall candidate detection."""

from itertools import pairwise

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from floorplan_extractor.dxf_polygon_extraction import SharedWallConfig
from floorplan_extractor.shared_walls import (
    detect_shared_wall_candidates,
    normalise_shared_walls,
)
from floorplan_extractor.yaml_construction import FlowList, polygons_to_rooms

MIN_GAP = 50.0
MAX_GAP = 130.0
MIN_OVERLAP_LENGTH = 250.0
MIN_OVERLAP_RATIO = 0.75


def _config() -> SharedWallConfig:
    return SharedWallConfig(
        enabled=True,
        min_gap=MIN_GAP,
        max_gap=MAX_GAP,
        angle_tolerance_degrees=2.0,
        min_overlap_ratio=MIN_OVERLAP_RATIO,
        min_overlap_length=MIN_OVERLAP_LENGTH,
        canonical_line="midline",
    )


def _room(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> Polygon:
    return Polygon(
        [
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        ]
    )


def _rooms(*polygons: Polygon) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"geometry": list(polygons)}, geometry="geometry")


def _canonical_segments(polygon: Polygon) -> set[tuple[tuple[float, float], ...]]:
    segments = set()
    coords = list(polygon.exterior.coords)
    for start, end in pairwise(coords):
        start_xy = (round(start[0], 6), round(start[1], 6))
        end_xy = (round(end[0], 6), round(end[1], 6))
        segments.add(tuple(sorted((start_xy, end_xy))))

    return segments


def test_detect_shared_wall_candidates_accepts_parallel_overlapping_gap() -> None:
    """Parallel wall faces with enough overlap and gap are candidates."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(500.0, 0.0, 900.0, 400.0),
    )

    result = detect_shared_wall_candidates(rooms, _config())

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.gap == pytest.approx(100.0)
    assert candidate.overlap_length == pytest.approx(400.0)
    assert candidate.overlap_ratio == pytest.approx(1.0)
    assert not any(r.reason == "ambiguous_match" for r in result.rejections)


def test_detect_shared_wall_candidates_rejects_insufficient_overlap() -> None:
    """Parallel wall faces with too little projected overlap are rejected."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(500.0, 300.0, 900.0, 700.0),
    )

    result = detect_shared_wall_candidates(rooms, _config())

    assert result.candidates == []
    assert any(
        rejection.reason == "insufficient_overlap_length"
        and rejection.overlap_length == pytest.approx(100.0)
        for rejection in result.rejections
    )


def test_detect_shared_wall_candidates_rejects_third_room_intersection() -> None:
    """Candidate wall faces are rejected when another room occupies the strip."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(500.0, 0.0, 900.0, 400.0),
        _room(425.0, 100.0, 475.0, 200.0),
    )

    result = detect_shared_wall_candidates(rooms, _config())

    assert result.candidates == []
    assert any(
        rejection.reason == "third_room_intersection"
        and rejection.blocking_room_id == 2
        for rejection in result.rejections
    )


def test_detect_shared_wall_candidates_rejects_ambiguous_matches() -> None:
    """One-to-many wall-face matches are reported as ambiguous."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(500.0, 0.0, 900.0, 400.0),
        _room(500.0, 0.0, 900.0, 400.0),
    )

    result = detect_shared_wall_candidates(rooms, _config())

    assert result.candidates == []
    assert sum(r.reason == "ambiguous_match" for r in result.rejections) == 2


def test_detect_shared_wall_candidates_does_not_mutate_rooms() -> None:
    """Candidate detection leaves input geometries unchanged."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(500.0, 0.0, 900.0, 400.0),
    )
    original_wkt = rooms.geometry.to_wkt().to_list()

    detect_shared_wall_candidates(rooms, _config())

    assert rooms.geometry.to_wkt().to_list() == original_wkt


def test_normalise_shared_walls_moves_accepted_pair_to_shared_midline() -> None:
    """Accepted paired wall faces are replaced with identical midline segments."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(500.0, 0.0, 900.0, 400.0),
    )
    detection = detect_shared_wall_candidates(rooms, _config())

    normalised = normalise_shared_walls(rooms, _config(), detection)

    expected_midline = ((450.0, 0.0), (450.0, 400.0))
    room_a_segments = _canonical_segments(normalised.geometry.iloc[0])
    room_b_segments = _canonical_segments(normalised.geometry.iloc[1])

    assert tuple(sorted(expected_midline)) in room_a_segments
    assert tuple(sorted(expected_midline)) in room_b_segments
    assert normalised.geometry.iloc[0].is_valid
    assert normalised.geometry.iloc[1].is_valid
    assert normalised.geometry.iloc[0].area > 0
    assert normalised.geometry.iloc[1].area > 0
    assert normalised["shared_wall_count"].to_list() == [1, 1]
    assert normalised["shared_wall_review"].to_list() == [False, False]


def test_normalise_shared_walls_leaves_rejected_candidates_unchanged() -> None:
    """Rejected detections remain diagnostic and do not alter geometry."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(500.0, 300.0, 900.0, 700.0),
    )
    original_wkt = rooms.geometry.to_wkt().to_list()
    detection = detect_shared_wall_candidates(rooms, _config())

    normalised = normalise_shared_walls(rooms, _config(), detection)

    assert detection.candidates == []
    assert normalised.geometry.to_wkt().to_list() == original_wkt
    assert normalised["shared_wall_count"].to_list() == [0, 0]
    assert normalised["shared_wall_review"].to_list() == [True, True]
    assert all(normalised["shared_wall_rejections"].apply(bool))


def test_normalise_shared_walls_leaves_ambiguous_candidates_unchanged() -> None:
    """Ambiguous candidate groups are not normalised."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(500.0, 0.0, 900.0, 400.0),
        _room(500.0, 0.0, 900.0, 400.0),
    )
    original_wkt = rooms.geometry.to_wkt().to_list()
    detection = detect_shared_wall_candidates(rooms, _config())

    normalised = normalise_shared_walls(rooms, _config(), detection)

    assert detection.candidates == []
    assert any(r.reason == "ambiguous_match" for r in detection.rejections)
    assert normalised.geometry.to_wkt().to_list() == original_wkt
    assert normalised["shared_wall_count"].to_list() == [0, 0, 0]


def test_normalised_shared_walls_keep_yaml_wall_schema() -> None:
    """Normalised geometry still serialises to [x1, y1, x2, y2] wall lists."""
    rooms = gpd.GeoDataFrame(
        {
            "room_name": ["Room A", "Room B"],
            "geometry": [
                _room(0.0, 0.0, 400.0, 400.0),
                _room(500.0, 0.0, 900.0, 400.0),
            ],
        },
        geometry="geometry",
    )
    detection = detect_shared_wall_candidates(rooms, _config())
    normalised = normalise_shared_walls(rooms, _config(), detection)

    serialised_rooms = polygons_to_rooms(normalised, "room_name")

    assert len(serialised_rooms) == 2
    assert all(
        isinstance(wall, FlowList) and len(wall) == 4
        for room in serialised_rooms
        for wall in room["walls"]
    )
