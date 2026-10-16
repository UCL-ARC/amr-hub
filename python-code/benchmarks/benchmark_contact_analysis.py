"""Compare spatially hashed contact detection with an all-pairs reference."""

# ruff: noqa: T201

from __future__ import annotations

import argparse
from collections.abc import Callable
from statistics import median
from time import perf_counter

import numpy as np

from amr_hub_abm.contact_analysis import (
    AgentTrack,
    ContactObservation,
    _sampling_interval,
    detect_contacts,
)

Detector = Callable[
    [list[AgentTrack], float],
    tuple[list[ContactObservation], int],
]


def make_random_walk_tracks(
    agent_count: int,
    step_count: int,
    seed: int,
    area_size: float,
    step_standard_deviation: float,
) -> list[AgentTrack]:
    """Create seeded 2D random walks stored as in-memory agent tracks."""
    rng = np.random.default_rng(seed)
    starting_positions = rng.uniform(0.0, area_size, size=(agent_count, 2))
    displacements = rng.normal(
        0.0,
        step_standard_deviation,
        size=(agent_count, step_count, 2),
    )
    positions = starting_positions[:, np.newaxis, :] + np.cumsum(displacements, axis=1)

    return [
        AgentTrack(
            name=f"patient_{agent_index}",
            positions_by_time={
                step: (
                    1,
                    0,
                    float(positions[agent_index, step, 0]),
                    float(positions[agent_index, step, 1]),
                )
                for step in range(step_count)
            },
        )
        for agent_index in range(agent_count)
    ]


def detect_contacts_pairwise(
    tracks: list[AgentTrack], distance_threshold: float
) -> tuple[list[ContactObservation], int]:
    """Run the former all-pairs contact search for comparison."""
    all_times = sorted({time for track in tracks for time in track.positions_by_time})
    interval = _sampling_interval(all_times)
    observations: list[ContactObservation] = []
    for track_index, track_a in enumerate(tracks):
        for track_b in tracks[track_index + 1 :]:
            for time in sorted(
                track_a.positions_by_time.keys() & track_b.positions_by_time.keys()
            ):
                building_a, floor_a, x_a, y_a = track_a.positions_by_time[time]
                building_b, floor_b, x_b, y_b = track_b.positions_by_time[time]
                if (building_a, floor_a) != (building_b, floor_b):
                    continue
                distance = float(np.hypot(x_a - x_b, y_a - y_b))
                if distance <= distance_threshold:
                    agent_a, agent_b = sorted((track_a.name, track_b.name))
                    observations.append(
                        ContactObservation(
                            time=time,
                            agent_a=agent_a,
                            agent_b=agent_b,
                            distance=distance,
                            building=building_a,
                            floor=floor_a,
                            midpoint_x=(x_a + x_b) / 2,
                            midpoint_y=(y_a + y_b) / 2,
                        )
                    )
    observations.sort(key=lambda item: (item.time, item.agent_a, item.agent_b))
    return observations, interval


def _time_detector(
    detector: Detector,
    tracks: list[AgentTrack],
    threshold: float,
    repeats: int,
) -> tuple[float, list[ContactObservation]]:
    """Return the median detector duration and its last observations."""
    durations: list[float] = []
    expected_observations: list[ContactObservation] | None = None
    for _ in range(repeats):
        started = perf_counter()
        observations, _ = detector(tracks, threshold)
        durations.append(perf_counter() - started)
        expected_observations = observations

    if expected_observations is None:
        msg = "At least one benchmark repeat is required"
        raise ValueError(msg)
    return median(durations), expected_observations


def build_parser() -> argparse.ArgumentParser:
    """Create the benchmark command-line parser."""
    parser = argparse.ArgumentParser(
        description="Compare spatial-hash contact detection to an all-pairs reference."
    )
    parser.add_argument("--agents", type=int, default=1000)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--area-size", type=float, default=10.0)
    parser.add_argument("--step-standard-deviation", type=float, default=0.05)
    parser.add_argument("--distance-threshold", type=float, default=0.1)
    return parser


def main() -> None:
    """Generate random walks, benchmark both detectors, and check parity."""
    args = build_parser().parse_args()
    if args.agents < 1 or args.steps < 1 or args.repeats < 1:
        build_parser().error("--agents, --steps, and --repeats must be positive")
    if args.area_size <= 0 or args.step_standard_deviation < 0:
        build_parser().error(
            "--area-size must be positive and --step-standard-deviation non-negative"
        )
    if args.distance_threshold < 0 or not np.isfinite(args.distance_threshold):
        build_parser().error("--distance-threshold must be finite and non-negative")

    tracks = make_random_walk_tracks(
        args.agents,
        args.steps,
        args.seed,
        args.area_size,
        args.step_standard_deviation,
    )
    pairwise_time, pairwise_observations = _time_detector(
        detect_contacts_pairwise,
        tracks,
        args.distance_threshold,
        args.repeats,
    )
    spatial_hash_time, spatial_hash_observations = _time_detector(
        detect_contacts,
        tracks,
        args.distance_threshold,
        args.repeats,
    )

    if pairwise_observations != spatial_hash_observations:
        msg = "Spatial-hash and all-pairs contact results do not match"
        raise RuntimeError(msg)

    print(f"Agents: {args.agents}; timesteps: {args.steps}; repeats: {args.repeats}")
    print(
        "Random walk: "
        f"seed={args.seed}, start in [0, {args.area_size}] for each axis, "
        f"per-axis step standard deviation={args.step_standard_deviation}"
    )
    print(f"Distance threshold: {args.distance_threshold}")
    print(f"Contact observations: {len(spatial_hash_observations)} (identical results)")
    print(f"All-pairs median: {pairwise_time:.3f}s")
    print(f"Spatial-hash median: {spatial_hash_time:.3f}s")
    print(f"Speedup: {pairwise_time / spatial_hash_time:.1f}x")


if __name__ == "__main__":
    main()
