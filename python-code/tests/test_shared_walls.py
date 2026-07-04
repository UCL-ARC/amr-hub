"""Tests for shared-wall candidate detection."""

from itertools import pairwise

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from floorplan_extractor.dxf_polygon_extraction import SharedWallConfig
from floorplan_extractor.shared_walls import (
    SharedWallCandidate,
    SharedWallDetectionResult,
    WallSegment,
    _repair_normalised_polygon,
    detect_shared_wall_candidates,
    normalise_shared_walls,
    rejection_overlap_lines,
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


def test_detect_shared_wall_candidates_flags_too_close_parallel_walls() -> None:
    """Parallel wall faces below the configured gap are visible diagnostics."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(430.0, 0.0, 830.0, 400.0),
    )

    detection = detect_shared_wall_candidates(rooms, _config())
    normalised = normalise_shared_walls(rooms, _config(), detection)

    assert detection.candidates == []
    assert any(
        rejection.reason == "gap_too_small" and rejection.gap == pytest.approx(30.0)
        for rejection in detection.rejections
    )
    assert normalised["shared_wall_review"].to_list() == [True, True]
    assert any(
        rejection["reason"] == "gap_too_small"
        for rejection in normalised["shared_wall_rejections"].iloc[0]
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


def test_detect_shared_wall_candidates_allows_disjoint_matches_on_long_wall() -> None:
    """A long corridor wall can match multiple non-overlapping room walls."""
    rooms = _rooms(
        _room(0.0, 0.0, 1000.0, 400.0),
        _room(0.0, 500.0, 400.0, 900.0),
        _room(600.0, 500.0, 1000.0, 900.0),
    )

    result = detect_shared_wall_candidates(rooms, _config())
    normalised = normalise_shared_walls(rooms, _config(), result)

    assert len(result.candidates) == 2
    assert not any(r.reason == "ambiguous_match" for r in result.rejections)
    assert normalised["shared_wall_count"].to_list() == [2, 1, 1]
    assert tuple(sorted(((0.0, 450.0), (400.0, 450.0)))) in _canonical_segments(
        normalised.geometry.iloc[0]
    )
    assert tuple(sorted(((600.0, 450.0), (1000.0, 450.0)))) in _canonical_segments(
        normalised.geometry.iloc[0]
    )


def test_detect_shared_wall_candidates_aggregates_partial_wall_coverage() -> None:
    """Disjoint partial matches are accepted when they jointly cover a wall."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 1000.0),
        _room(500.0, -250.0, 900.0, 400.0),
        _room(500.0, 600.0, 900.0, 1250.0),
    )

    result = detect_shared_wall_candidates(rooms, _config())
    normalised = normalise_shared_walls(rooms, _config(), result)

    assert len(result.candidates) == 2
    assert not any(
        rejection.reason == "insufficient_overlap_ratio"
        for rejection in result.rejections
    )
    assert normalised["shared_wall_count"].to_list() == [2, 1, 1]
    assert tuple(sorted(((450.0, 0.0), (450.0, 400.0)))) in _canonical_segments(
        normalised.geometry.iloc[0]
    )
    assert tuple(sorted(((450.0, 600.0), (450.0, 1000.0)))) in _canonical_segments(
        normalised.geometry.iloc[0]
    )


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


def test_normalise_shared_walls_uses_one_projection_axis_for_skewed_pair() -> None:
    """Slightly skewed reversed walls retain their real-world coordinates."""
    rooms = _rooms(
        Polygon(
            [
                (0.0, 0.0),
                (5000.0, 0.0),
                (5000.0, 400.0),
                (0.0, 400.0),
            ]
        ),
        Polygon(
            [
                (0.0, 500.0),
                (5000.0, 500.01),
                (5000.0, 900.0),
                (0.0, 900.0),
            ]
        ),
    )
    detection = detect_shared_wall_candidates(rooms, _config())

    normalised = normalise_shared_walls(rooms, _config(), detection)

    assert len(detection.candidates) == 1
    shared_segments = _canonical_segments(normalised.geometry.iloc[0]) & (
        _canonical_segments(normalised.geometry.iloc[1])
    )
    assert shared_segments == {((0.0, 450.0), (5000.0, 450.005))}


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


def test_normalise_shared_walls_rejects_pair_that_invalidates_geometry() -> None:
    """A failed pair is rejected without rolling back unrelated rooms."""
    rooms = _rooms(
        _room(0.0, 0.0, 1000.0, 100.0),
        _room(600.0, -200.0, 1000.0, -100.0),
    )
    first = WallSegment(
        room_id=0,
        segment_index=2,
        line=LineString([(1000.0, 100.0), (0.0, 100.0)]),
        start=(1000.0, 100.0),
        end=(0.0, 100.0),
        length=1000.0,
        angle_radians=0.0,
    )
    second = WallSegment(
        room_id=1,
        segment_index=2,
        line=LineString([(1000.0, -100.0), (600.0, -100.0)]),
        start=(1000.0, -100.0),
        end=(600.0, -100.0),
        length=400.0,
        angle_radians=0.0,
    )
    candidate = SharedWallCandidate(
        first=first,
        second=second,
        gap=200.0,
        overlap_length=400.0,
        overlap_ratio=1.0,
        overlap=(600.0, 1000.0),
        first_interval=(0.0, 400.0),
        second_interval=(0.0, 400.0),
        strip=Polygon(
            [
                (600.0, 100.0),
                (1000.0, 100.0),
                (1000.0, -100.0),
                (600.0, -100.0),
            ]
        ),
    )
    detection = SharedWallDetectionResult(candidates=[candidate], rejections=[])
    original_wkt = rooms.geometry.to_wkt().to_list()

    normalised = normalise_shared_walls(rooms, _config(), detection)
    applied = normalised.attrs["shared_wall_detection"]

    assert normalised.geometry.to_wkt().to_list() == original_wkt
    assert applied.candidates == []
    assert applied.rejections[0].reason == "normalisation_invalid_geometry"
    assert normalised["shared_wall_count"].to_list() == [0, 0]
    assert normalised["shared_wall_review"].to_list() == [True, True]


def test_normalise_shared_walls_collapses_near_duplicate_vertices() -> None:
    """Numerical DXF slivers do not invalidate an otherwise safe rewrite."""
    rooms = _rooms(
        _room(0.0, 0.0, 1950.0, 400.0),
        Polygon(
            [
                (2050.0 + 4e-9, 0.0),
                (2050.0, 0.0),
                (4000.0, 0.0),
                (4000.0, 400.0),
                (2050.0, 400.0),
            ]
        ),
    )
    detection = detect_shared_wall_candidates(rooms, _config())

    normalised = normalise_shared_walls(rooms, _config(), detection)
    applied = normalised.attrs["shared_wall_detection"]

    assert len(applied.candidates) == 1
    assert not any(
        rejection.reason == "normalisation_invalid_geometry"
        for rejection in applied.rejections
    )
    assert all(normalised.geometry.is_valid)


def test_repair_normalised_polygon_removes_zero_area_line_artifact() -> None:
    """A single polygon plus a retraced line is repaired conservatively."""
    polygon = Polygon(
        [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 10.0),
            (0.0, 10.0),
            (0.0, 0.0),
            (-5.0, 0.0),
            (0.0, 0.0),
        ]
    )

    repaired = _repair_normalised_polygon(polygon, [])

    assert repaired is not None
    assert repaired.is_valid
    assert repaired.area == pytest.approx(100.0)


def test_repair_normalised_polygon_rejects_multiple_polygon_parts() -> None:
    """A repair that would split a room into multiple polygons is rejected."""
    bow_tie = Polygon(
        [
            (0.0, 0.0),
            (10.0, 10.0),
            (0.0, 10.0),
            (10.0, 0.0),
            (0.0, 0.0),
        ]
    )

    assert _repair_normalised_polygon(bow_tie, []) is None


def test_rejection_overlap_lines_clip_source_segments() -> None:
    """Rejected diagnostics show only the paired projected overlap."""
    rooms = _rooms(
        _room(0.0, 0.0, 400.0, 400.0),
        _room(500.0, 300.0, 900.0, 700.0),
    )
    detection = detect_shared_wall_candidates(rooms, _config())
    rejection = next(
        rejection
        for rejection in detection.rejections
        if rejection.reason == "insufficient_overlap_length"
    )

    first, second = rejection_overlap_lines(rejection)

    assert first.length == pytest.approx(100.0)
    assert second.length == pytest.approx(100.0)
    for actual, expected in zip(
        sorted(first.coords),
        [(400.0, 300.0), (400.0, 400.0)],
        strict=True,
    ):
        assert actual == pytest.approx(expected)
    for actual, expected in zip(
        sorted(second.coords),
        [(500.0, 300.0), (500.0, 400.0)],
        strict=True,
    ):
        assert actual == pytest.approx(expected)


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
