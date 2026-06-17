"""Candidate detection for shared wall-face normalisation."""

from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from itertools import combinations, pairwise
from math import atan2, cos, pi, radians, sin

import geopandas as gpd
from shapely.geometry import LineString, Polygon

from floorplan_extractor.dxf_polygon_extraction import SharedWallConfig

XY = tuple[float, float]
MIN_SEGMENT_COORDINATES = 2
GEOMETRY_TOLERANCE = 1e-9


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
class SharedWallDetectionResult:
    """Candidate detection output for downstream diagnostics."""

    candidates: list[SharedWallCandidate]
    rejections: list[SharedWallRejection]


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
    candidates: list[SharedWallCandidate] = []
    rejections: list[SharedWallRejection] = []

    for first, second in combinations(segments, 2):
        if first.room_id == second.room_id:
            continue

        candidate, rejection = _evaluate_pair(first, second, rooms, config)
        if candidate is not None:
            candidates.append(candidate)
        elif rejection is not None:
            rejections.append(rejection)

    accepted, ambiguity_rejections = _reject_ambiguous_candidates(candidates)
    rejections.extend(ambiguity_rejections)

    return SharedWallDetectionResult(candidates=accepted, rejections=rejections)


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
    rooms: gpd.GeoDataFrame,
    config: SharedWallConfig,
) -> tuple[SharedWallCandidate | None, SharedWallRejection | None]:
    if not _is_near_parallel(first, second, config.angle_tolerance_degrees):
        return None, None

    gap = _perpendicular_gap(first, second)
    if gap < config.min_gap or gap > config.max_gap:
        return None, SharedWallRejection(first, second, "gap_out_of_range", gap=gap)

    overlap = _projected_overlap(first, second)
    overlap_length = overlap[1] - overlap[0]
    overlap_ratio = overlap_length / min(first.length, second.length)
    if overlap_length < config.min_overlap_length:
        return None, SharedWallRejection(
            first,
            second,
            "insufficient_overlap_length",
            gap=gap,
            overlap_length=overlap_length,
            overlap_ratio=overlap_ratio,
        )

    if overlap_ratio < config.min_overlap_ratio:
        return None, SharedWallRejection(
            first,
            second,
            "insufficient_overlap_ratio",
            gap=gap,
            overlap_length=overlap_length,
            overlap_ratio=overlap_ratio,
        )

    strip = _overlap_strip(first, second, overlap)
    blocking_room_id = _blocking_room_id(rooms, strip, {first.room_id, second.room_id})
    if blocking_room_id is not None:
        return None, SharedWallRejection(
            first,
            second,
            "third_room_intersection",
            gap=gap,
            overlap_length=overlap_length,
            overlap_ratio=overlap_ratio,
            blocking_room_id=blocking_room_id,
        )

    return (
        SharedWallCandidate(
            first=first,
            second=second,
            gap=gap,
            overlap_length=overlap_length,
            overlap_ratio=overlap_ratio,
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
    first_start = _point_at_projection(first, overlap[0])
    first_end = _point_at_projection(first, overlap[1])
    second_start = _point_at_projection(second, overlap[0])
    second_end = _point_at_projection(second, overlap[1])

    return Polygon([first_start, first_end, second_end, second_start])


def _blocking_room_id(
    rooms: gpd.GeoDataFrame,
    strip: Polygon,
    paired_room_ids: set[Hashable],
) -> Hashable | None:
    for room_id, geometry in rooms.geometry.items():
        if room_id in paired_room_ids:
            continue

        intersection = geometry.intersection(strip)
        if intersection.area > GEOMETRY_TOLERANCE:
            return room_id

    return None


def _reject_ambiguous_candidates(
    candidates: list[SharedWallCandidate],
) -> tuple[list[SharedWallCandidate], list[SharedWallRejection]]:
    segment_counts: dict[tuple[Hashable, int], int] = {}
    for candidate in candidates:
        for key in (candidate.first.key, candidate.second.key):
            segment_counts[key] = segment_counts.get(key, 0) + 1

    accepted: list[SharedWallCandidate] = []
    rejections: list[SharedWallRejection] = []

    for candidate in candidates:
        if (
            segment_counts[candidate.first.key] == 1
            and segment_counts[candidate.second.key] == 1
        ):
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


def _projection_range(
    segment: WallSegment,
    axis: tuple[float, float],
) -> tuple[float, float]:
    projections = [_dot(point, axis) for point in (segment.start, segment.end)]

    return (min(projections), max(projections))


def _point_at_projection(segment: WallSegment, projection: float) -> XY:
    axis = _unit_axis(segment)
    origin_projection = _dot(segment.start, axis)
    distance = projection - origin_projection

    return (
        segment.start[0] + axis[0] * distance,
        segment.start[1] + axis[1] * distance,
    )


def _unit_axis(segment: WallSegment) -> tuple[float, float]:
    return (cos(segment.angle_radians), sin(segment.angle_radians))


def _dot(first: Iterable[float], second: Iterable[float]) -> float:
    first_x, first_y = first
    second_x, second_y = second

    return (first_x * second_x) + (first_y * second_y)


def _xy(point: tuple[float, ...]) -> XY:
    return (float(point[0]), float(point[1]))
