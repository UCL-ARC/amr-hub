"""Synthetic floorplan fixtures for geometry regression tests."""

from collections.abc import Callable, Hashable
from dataclasses import dataclass

import geopandas as gpd
from shapely.geometry import LineString, Polygon

from floorplan_extractor.shared_walls import (
    SharedWallCandidate,
    SharedWallDetectionResult,
    WallSegment,
)

CandidateRecord = tuple[
    tuple[Hashable, int],
    tuple[Hashable, int],
    float,
    float,
    float,
]
RejectionRecord = tuple[
    tuple[Hashable, int],
    tuple[Hashable, int],
    str,
    float | None,
    float | None,
    float | None,
    Hashable | None,
]


@dataclass(frozen=True)
class FloorplanRegressionCase:
    """One synthetic extraction scenario and its accepted baseline."""

    name: str
    rooms: gpd.GeoDataFrame
    expected_geometry: tuple[Polygon, ...]
    expected_candidates: tuple[CandidateRecord, ...]
    expected_rejections: tuple[RejectionRecord, ...]
    expected_counts: tuple[int, ...]
    expected_review: tuple[bool, ...]
    detection_factory: Callable[[], SharedWallDetectionResult] | None = None
    doors: gpd.GeoDataFrame | None = None
    expected_doors: tuple[tuple[tuple[float, float, float, float], ...], ...] | None = (
        None
    )
    expected_door_report: tuple[tuple[str, int, bool], ...] | None = None


def rectangle(min_x: float, min_y: float, max_x: float, max_y: float) -> Polygon:
    """Create an axis-aligned synthetic room polygon."""
    return Polygon(
        [
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        ]
    )


def room_frame(*polygons: Polygon) -> gpd.GeoDataFrame:
    """Create a room GeoDataFrame with stable integer identifiers."""
    return gpd.GeoDataFrame({"geometry": list(polygons)}, geometry="geometry")


def _valid_expected_geometry() -> tuple[Polygon, Polygon]:
    return (
        Polygon(
            [
                (0.0, 0.0),
                (400.0, 0.0),
                (450.0, 0.0),
                (450.0, 400.0),
                (400.0, 400.0),
                (0.0, 400.0),
            ]
        ),
        Polygon(
            [
                (500.0, 0.0),
                (900.0, 0.0),
                (900.0, 400.0),
                (500.0, 400.0),
                (450.0, 400.0),
                (450.0, 0.0),
            ]
        ),
    )


def _invalid_normalisation_detection() -> SharedWallDetectionResult:
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
    return SharedWallDetectionResult(candidates=[candidate], rejections=[])


def regression_cases() -> tuple[FloorplanRegressionCase, ...]:
    """Return fresh synthetic cases covering accepted and rejected geometry."""
    separated_geometry = (
        rectangle(0.0, 0.0, 400.0, 400.0),
        rectangle(1000.0, 1000.0, 1400.0, 1400.0),
    )
    valid_rooms = (
        rectangle(0.0, 0.0, 400.0, 400.0),
        rectangle(500.0, 0.0, 900.0, 400.0),
    )
    ambiguous_geometry = (
        rectangle(0.0, 0.0, 400.0, 400.0),
        rectangle(500.0, 0.0, 900.0, 400.0),
        rectangle(500.0, 0.0, 900.0, 400.0),
    )
    obstruction_geometry = (
        rectangle(0.0, 0.0, 400.0, 400.0),
        rectangle(500.0, 0.0, 900.0, 400.0),
        rectangle(425.0, 100.0, 475.0, 200.0),
    )
    invalid_geometry = (
        rectangle(0.0, 0.0, 1000.0, 100.0),
        rectangle(600.0, -200.0, 1000.0, -100.0),
    )
    canonical_door_source = gpd.GeoDataFrame(
        {
            "EntityHandle": ["door-1", "door-1", "door-1"],
            "geometry": [
                LineString([(450.0, 150.0), (550.0, 150.0)]),
                LineString([(450.0, 250.0), (550.0, 250.0)]),
                LineString([(550.0, 150.0), (500.0, 200.0), (450.0, 250.0)]),
            ],
        },
        geometry="geometry",
    )

    valid_candidate: CandidateRecord = (
        (0, 1),
        (1, 3),
        100.0,
        400.0,
        1.0,
    )

    return (
        FloorplanRegressionCase(
            name="separated_rooms",
            rooms=room_frame(*separated_geometry),
            expected_geometry=separated_geometry,
            expected_candidates=(),
            expected_rejections=(),
            expected_counts=(0, 0),
            expected_review=(False, False),
        ),
        FloorplanRegressionCase(
            name="valid_shared_wall",
            rooms=room_frame(*valid_rooms),
            expected_geometry=_valid_expected_geometry(),
            expected_candidates=(valid_candidate,),
            expected_rejections=(),
            expected_counts=(1, 1),
            expected_review=(False, False),
        ),
        FloorplanRegressionCase(
            name="ambiguous_one_to_many",
            rooms=room_frame(*ambiguous_geometry),
            expected_geometry=ambiguous_geometry,
            expected_candidates=(),
            expected_rejections=(
                ((1, 0), (2, 0), "gap_too_small", 0.0, 400.0, 1.0, None),
                ((1, 1), (2, 1), "gap_too_small", 0.0, 400.0, 1.0, None),
                ((1, 2), (2, 2), "gap_too_small", 0.0, 400.0, 1.0, None),
                ((1, 3), (2, 3), "gap_too_small", 0.0, 400.0, 1.0, None),
                ((0, 1), (1, 3), "ambiguous_match", 100.0, 400.0, 1.0, None),
                ((0, 1), (2, 3), "ambiguous_match", 100.0, 400.0, 1.0, None),
            ),
            expected_counts=(0, 0, 0),
            expected_review=(True, True, True),
        ),
        FloorplanRegressionCase(
            name="third_room_obstruction",
            rooms=room_frame(*obstruction_geometry),
            expected_geometry=obstruction_geometry,
            expected_candidates=(),
            expected_rejections=(
                (
                    (0, 1),
                    (1, 3),
                    "third_room_intersection",
                    100.0,
                    400.0,
                    1.0,
                    2,
                ),
                (
                    (0, 1),
                    (2, 1),
                    "insufficient_overlap_length",
                    75.0,
                    100.0,
                    1.0,
                    None,
                ),
                (
                    (0, 1),
                    (2, 3),
                    "gap_too_small",
                    25.0,
                    100.0,
                    1.0,
                    None,
                ),
                (
                    (1, 3),
                    (2, 1),
                    "gap_too_small",
                    25.0,
                    100.0,
                    1.0,
                    None,
                ),
                (
                    (1, 3),
                    (2, 3),
                    "insufficient_overlap_length",
                    75.0,
                    100.0,
                    1.0,
                    None,
                ),
            ),
            expected_counts=(0, 0, 0),
            expected_review=(True, True, True),
        ),
        FloorplanRegressionCase(
            name="invalid_normalisation",
            rooms=room_frame(*invalid_geometry),
            expected_geometry=invalid_geometry,
            expected_candidates=(),
            expected_rejections=(
                (
                    (0, 2),
                    (1, 2),
                    "normalisation_invalid_geometry",
                    200.0,
                    400.0,
                    1.0,
                    None,
                ),
            ),
            expected_counts=(0, 0),
            expected_review=(True, True),
            detection_factory=_invalid_normalisation_detection,
        ),
        FloorplanRegressionCase(
            name="canonical_door_on_shared_boundary",
            rooms=room_frame(*valid_rooms),
            expected_geometry=_valid_expected_geometry(),
            expected_candidates=(valid_candidate,),
            expected_rejections=(),
            expected_counts=(1, 1),
            expected_review=(False, False),
            doors=canonical_door_source,
            expected_doors=(
                ((450.0, 150.0, 450.0, 250.0),),
                ((450.0, 150.0, 450.0, 250.0),),
            ),
            expected_door_report=(("door-1", 2, False),),
        ),
    )
