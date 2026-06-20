"""Measure exhaustive shared-wall candidate detection on synthetic room grids."""

# ruff: noqa: T201

import argparse
import platform
from collections.abc import Sequence
from statistics import median
from time import perf_counter

import geopandas as gpd
import shapely
from shapely.geometry import Polygon

from floorplan_extractor.shared_walls import (
    SharedWallConfig,
    detect_shared_wall_candidates,
)

DEFAULT_GRID_SIZES = (4, 8, 12)
DEFAULT_REPEAT = 3
DEFAULT_WARMUP = 1
ROOM_SIZE = 400.0
ROOM_GAP = 100.0
SEGMENTS_PER_ROOM = 4


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark exhaustive shared-wall detection using non-sensitive "
            "synthetic square-room grids."
        )
    )
    parser.add_argument(
        "--grid-sizes",
        type=int,
        nargs="+",
        default=DEFAULT_GRID_SIZES,
        help="Grid side lengths to measure (default: %(default)s).",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=DEFAULT_REPEAT,
        help="Measured runs per input size (default: %(default)s).",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP,
        help="Warm-up runs per input size (default: %(default)s).",
    )
    return parser.parse_args()


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


def _room_grid(side_length: int) -> gpd.GeoDataFrame:
    if side_length < 1:
        msg = "Grid sizes must be positive integers"
        raise ValueError(msg)

    stride = ROOM_SIZE + ROOM_GAP
    polygons = [
        Polygon(
            [
                (column * stride, row * stride),
                (column * stride + ROOM_SIZE, row * stride),
                (column * stride + ROOM_SIZE, row * stride + ROOM_SIZE),
                (column * stride, row * stride + ROOM_SIZE),
            ]
        )
        for row in range(side_length)
        for column in range(side_length)
    ]
    return gpd.GeoDataFrame({"geometry": polygons}, geometry="geometry")


def _measure(
    rooms: gpd.GeoDataFrame,
    config: SharedWallConfig,
    *,
    repeat: int,
    warmup: int,
) -> tuple[float, float, int, int]:
    for _ in range(warmup):
        detect_shared_wall_candidates(rooms, config)

    timings: list[float] = []
    candidate_count = 0
    rejection_count = 0
    for _ in range(repeat):
        start = perf_counter()
        result = detect_shared_wall_candidates(rooms, config)
        timings.append(perf_counter() - start)
        candidate_count = len(result.candidates)
        rejection_count = len(result.rejections)

    return median(timings), min(timings), candidate_count, rejection_count


def _validate_args(grid_sizes: Sequence[int], repeat: int, warmup: int) -> None:
    if any(size < 1 for size in grid_sizes):
        msg = "All grid sizes must be positive integers"
        raise ValueError(msg)
    if repeat < 1:
        msg = "--repeat must be at least 1"
        raise ValueError(msg)
    if warmup < 0:
        msg = "--warmup cannot be negative"
        raise ValueError(msg)


def main() -> None:
    """Run the benchmark and print machine details plus a Markdown table."""
    args = _parse_args()
    _validate_args(args.grid_sizes, args.repeat, args.warmup)
    config = _config()

    print(f"Python: {platform.python_version()}")
    print(f"Platform: {platform.platform()}")
    print(f"Shapely: {shapely.__version__}")
    print(f"Repeats: {args.repeat}; warm-up runs: {args.warmup}")
    print()
    print("| Grid | Rooms | Segments | Median (s) | Best (s) | Accepted | Rejected |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: | ---: |")

    for side_length in args.grid_sizes:
        rooms = _room_grid(side_length)
        median_seconds, best_seconds, candidates, rejections = _measure(
            rooms,
            config,
            repeat=args.repeat,
            warmup=args.warmup,
        )
        room_count = len(rooms)
        print(
            f"| {side_length}x{side_length} | {room_count} | "
            f"{room_count * SEGMENTS_PER_ROOM} | {median_seconds:.6f} | "
            f"{best_seconds:.6f} | {candidates} | {rejections} |"
        )


if __name__ == "__main__":
    main()
