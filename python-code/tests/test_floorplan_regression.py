"""Regression baseline for floorplan geometry and diagnostics."""

from typing import Any, cast

import pytest

from floorplan_extractor.dxf_polygon_extraction import attach_room_doors
from floorplan_extractor.shared_walls import (
    SharedWallCandidate,
    SharedWallConfig,
    SharedWallRejection,
    detect_shared_wall_candidates,
    normalise_shared_walls,
)
from tests.floorplan_geometry_assertions import (
    assert_geometry_equal,
    rounded_optional,
    sorted_records,
)
from tests.floorplan_regression_fixtures import (
    CandidateRecord,
    FloorplanRegressionCase,
    RejectionRecord,
    regression_cases,
)

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


def _candidate_record(candidate: SharedWallCandidate) -> CandidateRecord:
    return (
        (candidate.first.room_id, candidate.first.segment_index),
        (candidate.second.room_id, candidate.second.segment_index),
        round(candidate.gap, 6),
        round(candidate.overlap_length, 6),
        round(candidate.overlap_ratio, 6),
    )


def _rejection_record(rejection: SharedWallRejection) -> RejectionRecord:
    return (
        (rejection.first.room_id, rejection.first.segment_index),
        (rejection.second.room_id, rejection.second.segment_index),
        rejection.reason,
        rounded_optional(rejection.gap),
        rounded_optional(rejection.overlap_length),
        rounded_optional(rejection.overlap_ratio),
        rejection.blocking_room_id,
    )


def _summary_record(summary: dict[str, Any]) -> RejectionRecord:
    return (
        (
            cast("Hashable", summary["first_room_id"]),
            int(summary["first_segment_index"]),
        ),
        (
            cast("Hashable", summary["second_room_id"]),
            int(summary["second_segment_index"]),
        ),
        str(summary["reason"]),
        rounded_optional(summary["gap"]),
        rounded_optional(summary["overlap_length"]),
        rounded_optional(summary["overlap_ratio"]),
        cast("Hashable | None", summary["blocking_room_id"]),
    )


@pytest.mark.parametrize(
    "case",
    regression_cases(),
    ids=lambda case: case.name,
)
def test_floorplan_geometry_regression(case: FloorplanRegressionCase) -> None:
    """Current extraction geometry and review diagnostics remain stable."""
    detection = (
        case.detection_factory()
        if case.detection_factory is not None
        else detect_shared_wall_candidates(case.rooms, _config())
    )

    result = normalise_shared_walls(case.rooms, _config(), detection)
    if case.doors is not None:
        result = attach_room_doors(result, case.doors)

    applied = result.attrs["shared_wall_detection"]
    assert sorted_records(_candidate_record(item) for item in applied.candidates) == (
        sorted_records(case.expected_candidates)
    )
    assert sorted_records(_rejection_record(item) for item in applied.rejections) == (
        sorted_records(case.expected_rejections)
    )

    assert len(result) == len(case.expected_geometry)
    for actual, expected in zip(
        result.geometry,
        case.expected_geometry,
        strict=True,
    ):
        assert_geometry_equal(actual, expected)

    assert tuple(result["shared_wall_count"]) == case.expected_counts
    assert tuple(result["shared_wall_review"]) == case.expected_review

    for room_id, summaries in result["shared_wall_rejections"].items():
        expected = [
            rejection
            for rejection in case.expected_rejections
            if room_id in {rejection[0][0], rejection[1][0]}
        ]
        assert sorted_records(_summary_record(item) for item in summaries) == (
            sorted_records(expected)
        )

    if case.expected_doors is not None:
        actual_doors = tuple(
            tuple(tuple(float(value) for value in door) for door in room_doors)
            for room_doors in result["doors"]
        )
        assert actual_doors == case.expected_doors

    if case.expected_door_report is not None:
        actual_report = tuple(
            (
                str(item["EntityHandle"]),
                int(item["attached_room_count"]),
                bool(item["door_attachment_warning"]),
            )
            for item in result.attrs["door_attachment_report"]
        )
        assert actual_report == case.expected_door_report
