"""
Shared wall-face detection and normalisation.

Architectural room polygons commonly follow opposite faces of the same
physical wall. This module identifies compatible parallel overlaps and moves
accepted pairs to one common midline. Rejected candidates are retained as
diagnostic metadata so uncertain geometry can be reviewed without silently
changing room boundaries.
"""

from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from itertools import combinations, pairwise
from math import atan2, cos, pi, radians, sin

import geopandas as gpd
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

XY = tuple[float, float]
SegmentReplacement = tuple[float, XY, XY, XY, XY]
SegmentPair = tuple["WallSegment", "WallSegment"]
MIN_SEGMENT_COORDINATES = 2
GEOMETRY_TOLERANCE = 1e-9
COORDINATE_TOLERANCE = 1e-6
BOUNDARY_COVERAGE_TOLERANCE = 1e-4
MIN_BOUNDARY_COVERAGE_RATIO = 0.99
MAX_REPAIR_AREA_RELATIVE_DIFFERENCE = 1e-9
MAX_ATTR_REJECTIONS = 1000
REVIEW_REJECTION_REASONS: frozenset[str] = frozenset(
    {
        "ambiguous_match",
        "gap_too_small",
        "insufficient_overlap_length",
        "insufficient_overlap_ratio",
        "normalisation_invalid_geometry",
        "third_room_intersection",
    }
)


@dataclass(frozen=True)
class SharedWallConfig:
    """
    Configuration for optional shared-wall normalisation.

    Attributes
    ----------
    enabled : bool
        Whether shared-wall normalisation should run.
    min_gap : float
        Minimum distance between paired wall faces.
    max_gap : float
        Maximum distance between paired wall faces.
    angle_tolerance_degrees : float
        Maximum angle difference for wall faces to be considered parallel.
    min_overlap_ratio : float
        Minimum projected overlap ratio required for pairing.
    min_overlap_length : float
        Minimum projected overlap length required for pairing.
    canonical_line : str
        Strategy for choosing the replacement shared wall line.

    """

    enabled: bool = False
    min_gap: float = 50.0
    max_gap: float = 130.0
    angle_tolerance_degrees: float = 2.0
    min_overlap_ratio: float = 0.75
    min_overlap_length: float = 250.0
    canonical_line: str = "midline"


@dataclass(frozen=True)
class WallSegment:
    """A straight exterior segment from one room polygon."""

    room_id: Hashable
    segment_index: int
    line: LineString
    start: XY
    end: XY
    length: float
    angle_radians: float

    @property
    def key(self) -> tuple[Hashable, int]:
        """Return a stable key for matching and ambiguity checks."""
        return (self.room_id, self.segment_index)


@dataclass(frozen=True)
class SharedWallCandidate:
    """A candidate pair of wall faces that may represent one physical wall."""

    first: WallSegment
    second: WallSegment
    gap: float
    overlap_length: float
    overlap_ratio: float
    overlap: tuple[float, float]
    first_interval: tuple[float, float]
    second_interval: tuple[float, float]
    strip: Polygon


@dataclass(frozen=True)
class SharedWallRejection:
    """A rejected wall-face pair with diagnostic context."""

    first: WallSegment
    second: WallSegment
    reason: str
    gap: float | None = None
    overlap_length: float | None = None
    overlap_ratio: float | None = None
    blocking_room_id: Hashable | None = None


@dataclass(frozen=True)
class SharedWallPairMetrics:
    """Geometric measurements for a paired wall-face comparison."""

    gap: float
    overlap: tuple[float, float]
    overlap_length: float
    overlap_ratio: float


@dataclass(frozen=True)
class SharedWallDetectionResult:
    """Accepted and rejected shared-wall records for downstream diagnostics."""

    candidates: list[SharedWallCandidate]
    rejections: list[SharedWallRejection]


@dataclass(frozen=True)
class _RoomSpatialIndex:
    """Room geometries and their STRtree positions for obstruction checks."""

    room_ids: list[Hashable]
    geometries: list[BaseGeometry]
    tree: STRtree


def detect_shared_wall_candidates(
    rooms: gpd.GeoDataFrame,
    config: SharedWallConfig,
) -> SharedWallDetectionResult:
    """
    Detect possible shared wall-face pairs without mutating room geometry.

    Parameters
    ----------
    rooms : geopandas.GeoDataFrame
        Room polygons to inspect. The GeoDataFrame index is used as the room
        identifier in returned records.
    config : SharedWallConfig
        Geometric thresholds controlling candidate detection.

    Returns
    -------
    SharedWallDetectionResult
        Accepted candidates and rejected pair records.

    """
    segments = _extract_wall_segments(rooms)
    pairs = _indexed_segment_pairs(segments, config.max_gap)
    room_index = _build_room_spatial_index(rooms)
    return _detect_shared_wall_candidates_from_pairs(
        config,
        pairs,
        room_index,
    )


def _detect_shared_wall_candidates_exhaustive(
    rooms: gpd.GeoDataFrame,
    config: SharedWallConfig,
) -> SharedWallDetectionResult:
    """Return reference detection results using every cross-room segment pair."""
    segments = _extract_wall_segments(rooms)
    pairs = (
        (first, second)
        for first, second in combinations(segments, 2)
        if first.room_id != second.room_id
    )
    room_index = _build_room_spatial_index(rooms)
    return _detect_shared_wall_candidates_from_pairs(
        config,
        pairs,
        room_index,
    )


def _detect_shared_wall_candidates_from_pairs(
    config: SharedWallConfig,
    pairs: Iterable[SegmentPair],
    room_index: _RoomSpatialIndex,
) -> SharedWallDetectionResult:
    """Apply authoritative geometric checks to ordered segment pairs."""
    candidates: list[SharedWallCandidate] = []
    rejections: list[SharedWallRejection] = []

    for first, second in pairs:
        candidate, rejection = _evaluate_pair(first, second, room_index, config)
        if candidate is not None:
            candidates.append(candidate)
        elif rejection is not None:
            rejections.append(rejection)

    candidates, overlap_rejections = _reject_insufficient_overlap_candidates(
        candidates,
        config.min_overlap_ratio,
    )
    rejections.extend(overlap_rejections)

    accepted, ambiguity_rejections = _reject_ambiguous_candidates(candidates)
    rejections.extend(ambiguity_rejections)

    return SharedWallDetectionResult(candidates=accepted, rejections=rejections)


def _indexed_segment_pairs(
    segments: list[WallSegment],
    max_gap: float,
) -> list[SegmentPair]:
    """Return unique cross-room pairs selected by expanded segment envelopes."""
    if not segments:
        return []

    expanded_envelopes = [
        shapely.box(
            segment.line.bounds[0] - max_gap,
            segment.line.bounds[1] - max_gap,
            segment.line.bounds[2] + max_gap,
            segment.line.bounds[3] + max_gap,
        )
        for segment in segments
    ]
    tree = STRtree(expanded_envelopes)
    pairs: list[SegmentPair] = []

    for first_index, first in enumerate(segments):
        matching_indices = sorted(
            int(index) for index in tree.query(first.line.envelope)
        )
        for second_index in matching_indices:
            if second_index <= first_index:
                continue

            second = segments[second_index]
            if first.room_id == second.room_id:
                continue

            pairs.append((first, second))

    return pairs


def _build_room_spatial_index(rooms: gpd.GeoDataFrame) -> _RoomSpatialIndex:
    """Build one ordered room index for exact third-room obstruction checks."""
    room_ids = list(rooms.index)
    geometries = list(rooms.geometry)
    return _RoomSpatialIndex(
        room_ids=room_ids,
        geometries=geometries,
        tree=STRtree(geometries),
    )


def normalise_shared_walls(
    rooms: gpd.GeoDataFrame,
    config: SharedWallConfig,
    detection: SharedWallDetectionResult | None = None,
) -> gpd.GeoDataFrame:
    """
    Move accepted shared wall-face overlaps to a common midline.

    Parameters
    ----------
    rooms : geopandas.GeoDataFrame
        Labelled room polygons to normalise.
    config : SharedWallConfig
        Shared-wall configuration. If disabled, geometries are not changed.
    detection : SharedWallDetectionResult or None
        Candidate detection output. If omitted and config is enabled, detection
        is run using ``rooms`` and ``config``.

    Returns
    -------
    geopandas.GeoDataFrame
        A copy of ``rooms`` with updated geometries and the columns
        ``shared_wall_count``, ``shared_wall_rejections``, and
        ``shared_wall_review``. The complete detection result is also stored in
        ``result.attrs["shared_wall_detection"]``.

    """
    result = rooms.copy()

    if detection is None:
        detection = (
            detect_shared_wall_candidates(rooms, config)
            if config.enabled
            else SharedWallDetectionResult(candidates=[], rejections=[])
        )

    if config.enabled and detection.candidates:
        result.geometry, applied_candidates, application_rejections = (
            _normalised_geometry(result, detection.candidates)
        )
        detection = SharedWallDetectionResult(
            candidates=applied_candidates,
            rejections=[*detection.rejections, *application_rejections],
        )

    return _attach_review_metadata(result, detection)


def candidate_midline(candidate: SharedWallCandidate) -> LineString:
    """
    Return the canonical midline for an accepted shared-wall candidate.

    Parameters
    ----------
    candidate : SharedWallCandidate
        Candidate whose paired wall-face overlap should be represented.

    Returns
    -------
    shapely.geometry.LineString
        Line segment halfway between the paired overlapping wall faces.

    """
    first_start, first_end, second_start, second_end = _candidate_overlap_points(
        candidate
    )

    return LineString(
        [
            _midpoint(first_start, second_start),
            _midpoint(first_end, second_end),
        ]
    )


def rejection_overlap_lines(
    rejection: SharedWallRejection,
) -> tuple[LineString, LineString]:
    """
    Return source-wall lines clipped to a rejected pair's projected overlap.

    Parameters
    ----------
    rejection : SharedWallRejection
        Rejected wall-face pair to represent.

    Returns
    -------
    tuple[shapely.geometry.LineString, shapely.geometry.LineString]
        Corresponding overlap portions on the first and second wall faces.

    """
    overlap = _projected_overlap(rejection.first, rejection.second)
    axis = _unit_axis(rejection.first)

    return (
        LineString(
            [
                _point_at_axis_projection(rejection.first, axis, overlap[0]),
                _point_at_axis_projection(rejection.first, axis, overlap[1]),
            ]
        ),
        LineString(
            [
                _point_at_axis_projection(rejection.second, axis, overlap[0]),
                _point_at_axis_projection(rejection.second, axis, overlap[1]),
            ]
        ),
    )


def _extract_wall_segments(rooms: gpd.GeoDataFrame) -> list[WallSegment]:
    segments: list[WallSegment] = []

    for room_id, geometry in rooms.geometry.items():
        if not isinstance(geometry, Polygon) or geometry.is_empty:
            continue

        for segment_index, (start, end) in enumerate(
            pairwise(geometry.exterior.coords)
        ):
            start_xy = _xy(start)
            end_xy = _xy(end)
            line = LineString([start_xy, end_xy])
            if len(line.coords) < MIN_SEGMENT_COORDINATES:
                continue
            if line.length <= GEOMETRY_TOLERANCE:
                continue

            dx = end_xy[0] - start_xy[0]
            dy = end_xy[1] - start_xy[1]
            segments.append(
                WallSegment(
                    room_id=room_id,
                    segment_index=segment_index,
                    line=line,
                    start=start_xy,
                    end=end_xy,
                    length=float(line.length),
                    angle_radians=atan2(dy, dx) % pi,
                )
            )

    return segments


def _evaluate_pair(
    first: WallSegment,
    second: WallSegment,
    room_index: _RoomSpatialIndex,
    config: SharedWallConfig,
) -> tuple[SharedWallCandidate | None, SharedWallRejection | None]:
    if not _is_near_parallel(first, second, config.angle_tolerance_degrees):
        return None, None

    gap = _perpendicular_gap(first, second)
    if gap > config.max_gap:
        return None, SharedWallRejection(first, second, "gap_too_large", gap=gap)

    overlap = _projected_overlap(first, second)
    overlap_length = overlap[1] - overlap[0]
    overlap_ratio = overlap_length / min(first.length, second.length)
    if overlap_length <= GEOMETRY_TOLERANCE:
        return None, None

    metrics = SharedWallPairMetrics(
        gap=gap,
        overlap=overlap,
        overlap_length=overlap_length,
        overlap_ratio=overlap_ratio,
    )

    if gap < config.min_gap:
        return None, SharedWallRejection(
            first,
            second,
            "gap_too_small",
            gap=metrics.gap,
            overlap_length=metrics.overlap_length,
            overlap_ratio=metrics.overlap_ratio,
        )

    return _evaluate_overlapping_pair(
        first,
        second,
        room_index,
        config,
        metrics,
    )


def _evaluate_overlapping_pair(
    first: WallSegment,
    second: WallSegment,
    room_index: _RoomSpatialIndex,
    config: SharedWallConfig,
    metrics: SharedWallPairMetrics,
) -> tuple[SharedWallCandidate | None, SharedWallRejection | None]:
    if metrics.overlap_length < config.min_overlap_length:
        return None, SharedWallRejection(
            first,
            second,
            "insufficient_overlap_length",
            gap=metrics.gap,
            overlap_length=metrics.overlap_length,
            overlap_ratio=metrics.overlap_ratio,
        )

    strip = _overlap_strip(first, second, metrics.overlap)
    blocking_room_id = _blocking_room_id(
        room_index,
        strip,
        {first.room_id, second.room_id},
    )
    if blocking_room_id is not None:
        return None, SharedWallRejection(
            first,
            second,
            "third_room_intersection",
            gap=metrics.gap,
            overlap_length=metrics.overlap_length,
            overlap_ratio=metrics.overlap_ratio,
            blocking_room_id=blocking_room_id,
        )

    return (
        SharedWallCandidate(
            first=first,
            second=second,
            gap=metrics.gap,
            overlap_length=metrics.overlap_length,
            overlap_ratio=metrics.overlap_ratio,
            overlap=metrics.overlap,
            first_interval=_segment_interval(first, metrics.overlap, _unit_axis(first)),
            second_interval=_segment_interval(
                second,
                metrics.overlap,
                _unit_axis(first),
            ),
            strip=strip,
        ),
        None,
    )


def _is_near_parallel(
    first: WallSegment,
    second: WallSegment,
    angle_tolerance_degrees: float,
) -> bool:
    angle_delta = abs(first.angle_radians - second.angle_radians)
    angle_delta = min(angle_delta, pi - angle_delta)

    return angle_delta <= radians(angle_tolerance_degrees)


def _perpendicular_gap(first: WallSegment, second: WallSegment) -> float:
    axis = _unit_axis(first)
    normal = (-axis[1], axis[0])
    offset = (second.start[0] - first.start[0], second.start[1] - first.start[1])

    return abs(_dot(offset, normal))


def _projected_overlap(first: WallSegment, second: WallSegment) -> tuple[float, float]:
    axis = _unit_axis(first)
    first_range = _projection_range(first, axis)
    second_range = _projection_range(second, axis)

    overlap_start = max(first_range[0], second_range[0])
    overlap_end = min(first_range[1], second_range[1])

    return (overlap_start, max(overlap_start, overlap_end))


def _overlap_strip(
    first: WallSegment,
    second: WallSegment,
    overlap: tuple[float, float],
) -> Polygon:
    axis = _unit_axis(first)
    first_start = _point_at_axis_projection(first, axis, overlap[0])
    first_end = _point_at_axis_projection(first, axis, overlap[1])
    second_start = _point_at_axis_projection(second, axis, overlap[0])
    second_end = _point_at_axis_projection(second, axis, overlap[1])

    return Polygon([first_start, first_end, second_end, second_start])


def _blocking_room_id(
    room_index: _RoomSpatialIndex,
    strip: Polygon,
    paired_room_ids: set[Hashable],
) -> Hashable | None:
    if not strip.is_valid:
        strip = shapely.make_valid(strip)

    matching_indices = sorted(int(index) for index in room_index.tree.query(strip))
    for room_index_position in matching_indices:
        room_id = room_index.room_ids[room_index_position]
        if room_id in paired_room_ids:
            continue

        geometry = room_index.geometries[room_index_position]
        room_geometry = (
            shapely.make_valid(geometry) if not geometry.is_valid else geometry
        )

        intersection = room_geometry.intersection(strip)
        if intersection.area > GEOMETRY_TOLERANCE:
            return room_id

    return None


def _reject_insufficient_overlap_candidates(
    candidates: list[SharedWallCandidate],
    min_overlap_ratio: float,
) -> tuple[list[SharedWallCandidate], list[SharedWallRejection]]:
    candidates_by_segment: dict[tuple[Hashable, int], list[SharedWallCandidate]] = {}
    for candidate in candidates:
        candidates_by_segment.setdefault(candidate.first.key, []).append(candidate)
        candidates_by_segment.setdefault(candidate.second.key, []).append(candidate)

    accepted: list[SharedWallCandidate] = []
    rejections: list[SharedWallRejection] = []

    for candidate in candidates:
        if candidate.overlap_ratio >= min_overlap_ratio or any(
            _aggregate_overlap_ratio(segment, candidates_by_segment[segment.key])
            >= min_overlap_ratio
            for segment in (candidate.first, candidate.second)
        ):
            accepted.append(candidate)
            continue

        rejections.append(
            SharedWallRejection(
                first=candidate.first,
                second=candidate.second,
                reason="insufficient_overlap_ratio",
                gap=candidate.gap,
                overlap_length=candidate.overlap_length,
                overlap_ratio=candidate.overlap_ratio,
            )
        )

    return accepted, rejections


def _aggregate_overlap_ratio(
    segment: WallSegment,
    candidates: list[SharedWallCandidate],
) -> float:
    intervals = [
        (
            candidate.first_interval
            if candidate.first.key == segment.key
            else candidate.second_interval
        )
        for candidate in candidates
    ]

    return _merged_interval_length(intervals) / segment.length


def _merged_interval_length(intervals: list[tuple[float, float]]) -> float:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + GEOMETRY_TOLERANCE:
            merged.append((start, end))
            continue

        merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    return sum(end - start for start, end in merged)


def _reject_ambiguous_candidates(
    candidates: list[SharedWallCandidate],
) -> tuple[list[SharedWallCandidate], list[SharedWallRejection]]:
    candidates_by_segment: dict[tuple[Hashable, int], list[SharedWallCandidate]] = {}
    for candidate in candidates:
        candidates_by_segment.setdefault(candidate.first.key, []).append(candidate)
        candidates_by_segment.setdefault(candidate.second.key, []).append(candidate)

    accepted: list[SharedWallCandidate] = []
    rejections: list[SharedWallRejection] = []

    for candidate in candidates:
        if not _has_overlapping_competitor(candidate, candidates_by_segment):
            accepted.append(candidate)
            continue

        rejections.append(
            SharedWallRejection(
                first=candidate.first,
                second=candidate.second,
                reason="ambiguous_match",
                gap=candidate.gap,
                overlap_length=candidate.overlap_length,
                overlap_ratio=candidate.overlap_ratio,
            )
        )

    return accepted, rejections


def _has_overlapping_competitor(
    candidate: SharedWallCandidate,
    candidates_by_segment: dict[tuple[Hashable, int], list[SharedWallCandidate]],
) -> bool:
    for segment, interval in (
        (candidate.first, candidate.first_interval),
        (candidate.second, candidate.second_interval),
    ):
        for competitor in candidates_by_segment[segment.key]:
            if competitor is candidate:
                continue

            competitor_interval = (
                competitor.first_interval
                if competitor.first.key == segment.key
                else competitor.second_interval
            )
            if (
                _interval_overlap_length(interval, competitor_interval)
                > GEOMETRY_TOLERANCE
            ):
                return True

    return False


def _candidate_replacements(
    candidates: list[SharedWallCandidate],
) -> dict[tuple[Hashable, int], list[SegmentReplacement]]:
    replacements: dict[tuple[Hashable, int], list[SegmentReplacement]] = {}

    for candidate in candidates:
        first_midline, second_midline = _midline_replacements(candidate)
        replacements.setdefault(candidate.first.key, []).append(first_midline)
        replacements.setdefault(candidate.second.key, []).append(second_midline)

    for segment_replacements in replacements.values():
        segment_replacements.sort(key=lambda r: r[0])

    return replacements


def _midline_replacements(
    candidate: SharedWallCandidate,
) -> tuple[SegmentReplacement, SegmentReplacement]:
    first_start, first_end, second_start, second_end = _candidate_overlap_points(
        candidate
    )

    midline = (
        _midpoint(first_start, second_start),
        _midpoint(first_end, second_end),
    )

    return (
        _orient_replacement(candidate.first, (first_start, first_end), midline),
        _orient_replacement(candidate.second, (second_start, second_end), midline),
    )


def _orient_replacement(
    segment: WallSegment,
    overlap: tuple[XY, XY],
    midline: tuple[XY, XY],
) -> SegmentReplacement:
    start_distance = segment.line.project(Point(overlap[0]))
    end_distance = segment.line.project(Point(overlap[1]))

    if start_distance <= end_distance:
        return (start_distance, overlap[0], midline[0], midline[1], overlap[1])

    return (end_distance, overlap[1], midline[1], midline[0], overlap[0])


def _normalised_geometry(
    rooms: gpd.GeoDataFrame,
    candidates: list[SharedWallCandidate],
) -> tuple[
    gpd.GeoSeries,
    list[SharedWallCandidate],
    list[SharedWallRejection],
]:
    geometries = rooms.geometry.copy()
    candidates_by_room: dict[Hashable, list[SharedWallCandidate]] = {
        room_id: [] for room_id in rooms.index
    }
    applied: list[SharedWallCandidate] = []
    rejections: list[SharedWallRejection] = []

    ordered_candidates = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.overlap_length,
            -candidate.overlap_ratio,
            candidate.gap,
        ),
    )
    for candidate in ordered_candidates:
        room_ids = (candidate.first.room_id, candidate.second.room_id)
        updated: dict[Hashable, Polygon] = {}

        for room_id in room_ids:
            geometry = rooms.geometry.loc[room_id]
            if not isinstance(geometry, Polygon) or geometry.is_empty:
                break

            room_candidates = [*candidates_by_room[room_id], candidate]
            replacements = _candidate_replacements(room_candidates)
            polygon = _normalise_polygon(room_id, geometry, replacements)
            if not polygon.is_valid:
                repaired = _repair_normalised_polygon(polygon, room_candidates)
                if repaired is None:
                    break
                polygon = repaired

            if polygon.area <= GEOMETRY_TOLERANCE:
                break

            updated[room_id] = polygon
        else:
            applied.append(candidate)
            for room_id, polygon in updated.items():
                candidates_by_room[room_id].append(candidate)
                geometries.loc[room_id] = polygon
            continue

        rejections.append(
            SharedWallRejection(
                first=candidate.first,
                second=candidate.second,
                reason="normalisation_invalid_geometry",
                gap=candidate.gap,
                overlap_length=candidate.overlap_length,
                overlap_ratio=candidate.overlap_ratio,
            )
        )

    return geometries, applied, rejections


def _repair_normalised_polygon(
    polygon: Polygon,
    candidates: list[SharedWallCandidate],
) -> Polygon | None:
    repaired = shapely.make_valid(polygon)
    polygons = _polygon_parts(repaired)
    if len(polygons) != 1:
        return None

    repaired_polygon = polygons[0]
    area_tolerance = max(1.0, polygon.area) * MAX_REPAIR_AREA_RELATIVE_DIFFERENCE
    if abs(repaired_polygon.area - polygon.area) > area_tolerance:
        return None

    if not all(
        _boundary_contains_midline(repaired_polygon, candidate)
        for candidate in candidates
    ):
        return None

    return repaired_polygon


def _polygon_parts(geometry: shapely.Geometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if not hasattr(geometry, "geoms"):
        return []

    return [
        polygon for component in geometry.geoms for polygon in _polygon_parts(component)
    ]


def _boundary_contains_midline(
    polygon: Polygon,
    candidate: SharedWallCandidate,
) -> bool:
    midline = candidate_midline(candidate)
    if midline.length <= GEOMETRY_TOLERANCE:
        return True

    covered_length = (
        polygon.boundary.buffer(BOUNDARY_COVERAGE_TOLERANCE)
        .intersection(midline)
        .length
    )

    return covered_length / midline.length >= MIN_BOUNDARY_COVERAGE_RATIO


def _normalise_polygon(
    room_id: Hashable,
    polygon: Polygon,
    replacements: dict[tuple[Hashable, int], list[SegmentReplacement]],
) -> Polygon:
    coords = [_xy(coord) for coord in polygon.exterior.coords]
    if len(coords) < 2:
        return polygon

    updated: list[XY] = []
    for segment_index, (start, end) in enumerate(pairwise(coords)):
        if not updated:
            updated.append(start)

        segment_replacements = replacements.get((room_id, segment_index))
        if segment_replacements is None:
            _append_distinct(updated, end)
            continue

        for replacement in segment_replacements:
            _, overlap_start, mid_start, mid_end, overlap_end = replacement
            _append_distinct(updated, overlap_start)
            _append_distinct(updated, mid_start)
            _append_distinct(updated, mid_end)
            _append_distinct(updated, overlap_end)
        _append_distinct(updated, end)

    if not _coords_close(updated[0], updated[-1]):
        updated.append(updated[0])
    else:
        updated[-1] = updated[0]

    return Polygon(updated, holes=list(polygon.interiors))


def _attach_review_metadata(
    rooms: gpd.GeoDataFrame,
    detection: SharedWallDetectionResult,
) -> gpd.GeoDataFrame:
    result = rooms.copy()
    counts: dict[Hashable, int] = dict.fromkeys(result.index, 0)
    rejections: dict[Hashable, list[dict[str, object]]] = {
        room_id: [] for room_id in result.index
    }

    for candidate in detection.candidates:
        counts[candidate.first.room_id] = counts.get(candidate.first.room_id, 0) + 1
        counts[candidate.second.room_id] = counts.get(candidate.second.room_id, 0) + 1

    for rejection in detection.rejections:
        if rejection.reason not in REVIEW_REJECTION_REASONS:
            continue

        rejection_summary = _rejection_summary(rejection)
        for room_id in (rejection.first.room_id, rejection.second.room_id):
            if room_id in rejections:
                rejections[room_id].append(rejection_summary)

    result["shared_wall_count"] = [counts.get(room_id, 0) for room_id in result.index]
    result["shared_wall_rejections"] = [
        rejections.get(room_id, []) for room_id in result.index
    ]
    result["shared_wall_review"] = [
        bool(rejections.get(room_id, [])) for room_id in result.index
    ]
    result.attrs["shared_wall_detection"] = SharedWallDetectionResult(
        candidates=detection.candidates,
        rejections=[
            rejection
            for rejection in detection.rejections
            if rejection.reason in REVIEW_REJECTION_REASONS
        ][:MAX_ATTR_REJECTIONS],
    )

    return result


def _rejection_summary(rejection: SharedWallRejection) -> dict[str, object]:
    return {
        "reason": rejection.reason,
        "first_room_id": rejection.first.room_id,
        "first_segment_index": rejection.first.segment_index,
        "second_room_id": rejection.second.room_id,
        "second_segment_index": rejection.second.segment_index,
        "gap": rejection.gap,
        "overlap_length": rejection.overlap_length,
        "overlap_ratio": rejection.overlap_ratio,
        "blocking_room_id": rejection.blocking_room_id,
    }


def _projection_range(
    segment: WallSegment,
    axis: tuple[float, float],
) -> tuple[float, float]:
    projections = [_dot(point, axis) for point in (segment.start, segment.end)]

    return (min(projections), max(projections))


def _segment_interval(
    segment: WallSegment,
    overlap: tuple[float, float],
    projection_axis: tuple[float, float],
) -> tuple[float, float]:
    overlap_start = _point_at_axis_projection(
        segment,
        projection_axis,
        overlap[0],
    )
    overlap_end = _point_at_axis_projection(
        segment,
        projection_axis,
        overlap[1],
    )

    return tuple(
        sorted(
            (
                segment.line.project(Point(overlap_start)),
                segment.line.project(Point(overlap_end)),
            )
        )
    )


def _interval_overlap_length(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    overlap_start = max(first[0], second[0])
    overlap_end = min(first[1], second[1])

    return max(0.0, overlap_end - overlap_start)


def _candidate_overlap_points(
    candidate: SharedWallCandidate,
) -> tuple[XY, XY, XY, XY]:
    axis = _unit_axis(candidate.first)

    return (
        _point_at_axis_projection(candidate.first, axis, candidate.overlap[0]),
        _point_at_axis_projection(candidate.first, axis, candidate.overlap[1]),
        _point_at_axis_projection(candidate.second, axis, candidate.overlap[0]),
        _point_at_axis_projection(candidate.second, axis, candidate.overlap[1]),
    )


def _point_at_axis_projection(
    segment: WallSegment,
    projection_axis: tuple[float, float],
    projection: float,
) -> XY:
    segment_axis = _unit_axis(segment)
    axis_alignment = _dot(segment_axis, projection_axis)
    distance = (projection - _dot(segment.start, projection_axis)) / axis_alignment

    return (
        segment.start[0] + segment_axis[0] * distance,
        segment.start[1] + segment_axis[1] * distance,
    )


def _unit_axis(segment: WallSegment) -> tuple[float, float]:
    return (cos(segment.angle_radians), sin(segment.angle_radians))


def _dot(first: Iterable[float], second: Iterable[float]) -> float:
    first_x, first_y = first
    second_x, second_y = second

    return (first_x * second_x) + (first_y * second_y)


def _xy(point: tuple[float, ...]) -> XY:
    return (float(point[0]), float(point[1]))


def _midpoint(first: XY, second: XY) -> XY:
    return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)


def _append_distinct(coords: list[XY], point: XY) -> None:
    if not _coords_close(coords[-1], point):
        coords.append(point)


def _coords_close(first: XY, second: XY) -> bool:
    return (
        abs(first[0] - second[0]) <= COORDINATE_TOLERANCE
        and abs(first[1] - second[1]) <= COORDINATE_TOLERANCE
    )
