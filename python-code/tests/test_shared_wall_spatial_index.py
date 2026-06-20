"""Tests for indexed shared-wall broad-phase selection."""

from itertools import combinations

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from floorplan_extractor.shared_walls import (
    REVIEW_REJECTION_REASONS,
    SharedWallCandidate,
    SharedWallConfig,
    SharedWallDetectionResult,
    SharedWallRejection,
    _detect_shared_wall_candidates_exhaustive,
    _extract_wall_segments,
    _indexed_segment_pairs,
    detect_shared_wall_candidates,
)
from tests.floorplan_regression_fixtures import (
    FloorplanRegressionCase,
    regression_cases,
)


def _config() -> SharedWallConfig:
    return SharedWallConfig(
        enabled=True,
        min_gap=50.0,
        max_gap=130.0,
        angle_tolerance_degrees=2.0,
        min_overlap_ratio=0.75,
        min_overlap_length=250.0,
        canonical_line="midline",
    )


def _candidate_signature(
    candidate: SharedWallCandidate,
) -> tuple[object, ...]:
    return (
        candidate.first.key,
        candidate.second.key,
        round(candidate.gap, 6),
        round(candidate.overlap_length, 6),
        round(candidate.overlap_ratio, 6),
        tuple(round(value, 6) for value in candidate.overlap),
    )


def _rejection_signature(
    rejection: SharedWallRejection,
) -> tuple[object, ...]:
    return (
        rejection.first.key,
        rejection.second.key,
        rejection.reason,
        None if rejection.gap is None else round(rejection.gap, 6),
        (
            None
            if rejection.overlap_length is None
            else round(rejection.overlap_length, 6)
        ),
        (
            None
            if rejection.overlap_ratio is None
            else round(rejection.overlap_ratio, 6)
        ),
        rejection.blocking_room_id,
    )


def _material_signatures(
    result: SharedWallDetectionResult,
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    candidates = [_candidate_signature(candidate) for candidate in result.candidates]
    rejections = [
        _rejection_signature(rejection)
        for rejection in result.rejections
        if rejection.reason in REVIEW_REJECTION_REASONS
    ]
    return candidates, rejections


def _room_grid(side_length: int) -> gpd.GeoDataFrame:
    room_size = 400.0
    stride = 500.0
    polygons = [
        Polygon(
            [
                (column * stride, row * stride),
                (column * stride + room_size, row * stride),
                (column * stride + room_size, row * stride + room_size),
                (column * stride, row * stride + room_size),
            ]
        )
        for row in range(side_length)
        for column in range(side_length)
    ]
    return gpd.GeoDataFrame({"geometry": polygons}, geometry="geometry")


@pytest.mark.parametrize(
    "case",
    regression_cases(),
    ids=lambda case: case.name,
)
def test_indexed_detection_matches_exhaustive_regression_fixtures(
    case: FloorplanRegressionCase,
) -> None:
    """Indexed detection preserves candidates and review-relevant rejections."""
    indexed = detect_shared_wall_candidates(case.rooms, _config())
    exhaustive = _detect_shared_wall_candidates_exhaustive(case.rooms, _config())

    assert _material_signatures(indexed) == _material_signatures(exhaustive)


@pytest.mark.parametrize("side_length", [2, 4, 6])
def test_indexed_detection_matches_exhaustive_generated_grids(
    side_length: int,
) -> None:
    """Generated layouts retain exhaustive narrow-phase outcomes."""
    rooms = _room_grid(side_length)

    indexed = detect_shared_wall_candidates(rooms, _config())
    exhaustive = _detect_shared_wall_candidates_exhaustive(rooms, _config())

    assert _material_signatures(indexed) == _material_signatures(exhaustive)


def test_indexed_pairs_are_unique_cross_room_and_deterministic() -> None:
    """Broad-phase pairs exclude self, duplicate, and same-room comparisons."""
    rooms = _room_grid(3)
    segments = _extract_wall_segments(rooms)
    segment_positions = {
        segment.key: position for position, segment in enumerate(segments)
    }

    first_run = _indexed_segment_pairs(segments, _config().max_gap)
    second_run = _indexed_segment_pairs(segments, _config().max_gap)
    first_keys = [(first.key, second.key) for first, second in first_run]
    second_keys = [(first.key, second.key) for first, second in second_run]

    assert first_keys == second_keys
    assert len(first_keys) == len(set(first_keys))
    assert all(first.room_id != second.room_id for first, second in first_run)
    assert all(
        segment_positions[first.key] < segment_positions[second.key]
        for first, second in first_run
    )


def test_indexed_detection_result_order_is_deterministic() -> None:
    """Repeated indexed detections retain candidate and rejection ordering."""
    rooms = _room_grid(4)

    first = detect_shared_wall_candidates(rooms, _config())
    second = detect_shared_wall_candidates(rooms, _config())

    assert _material_signatures(first) == _material_signatures(second)


def test_indexed_broad_phase_reduces_generated_pair_count() -> None:
    """A separated grid selects substantially fewer pairs than exhaustive search."""
    rooms = _room_grid(8)
    segments = _extract_wall_segments(rooms)
    exhaustive_pair_count = sum(
        first.room_id != second.room_id for first, second in combinations(segments, 2)
    )

    indexed_pairs = _indexed_segment_pairs(segments, _config().max_gap)

    assert len(indexed_pairs) < exhaustive_pair_count / 4
