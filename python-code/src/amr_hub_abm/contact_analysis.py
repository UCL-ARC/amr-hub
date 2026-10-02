"""Analyse recorded agent trajectories for pairwise proximity contacts."""

from __future__ import annotations

import argparse
import csv
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import numpy as np
from matplotlib import pyplot as plt

logger = logging.getLogger(__name__)
TRAJECTORY_FILENAME = re.compile(
    r"agent_(?P<agent_type>.+)_(?P<agent_id>\d+)_trajectory\.csv$"
)
REQUIRED_COLUMNS = {"time", "building", "floor", "x", "y"}


@dataclass(frozen=True)
class AgentTrack:
    """Recorded positions and spatial identifiers for one agent."""

    name: str
    positions_by_time: dict[int, tuple[int, int, float, float]]


@dataclass(frozen=True)
class ContactObservation:
    """A pair of agents in contact at one recorded timestep."""

    time: int
    agent_a: str
    agent_b: str
    distance: float
    building: int
    floor: int
    midpoint_x: float
    midpoint_y: float


@dataclass(frozen=True)
class ContactEpisode:
    """An uninterrupted contact interval for one agent pair."""

    agent_a: str
    agent_b: str
    start_time: int
    end_time: int
    duration: int
    observations: int


def _read_track(path: Path) -> AgentTrack:
    """Load one recorded agent trajectory CSV."""
    match = TRAJECTORY_FILENAME.fullmatch(path.name)
    if match is None:
        msg = f"Unexpected trajectory filename: {path.name}"
        raise ValueError(msg)

    positions_by_time: dict[int, tuple[int, int, float, float]] = {}
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = set(reader.fieldnames or ())
        missing = REQUIRED_COLUMNS - columns
        if missing:
            msg = f"{path} is missing required columns: {', '.join(sorted(missing))}"
            raise ValueError(msg)

        for row_number, row in enumerate(reader, start=2):
            try:
                # time/building/floor are written as floats (e.g. "1.0e+02") by
                # np.savetxt, since they share a homogeneous float array with x/y.
                time = int(float(row["time"]))
                building = int(float(row["building"]))
                floor = int(float(row["floor"]))
                x = float(row["x"])
                y = float(row["y"])
            except (TypeError, ValueError) as error:
                msg = f"Invalid trajectory data in {path}, row {row_number}"
                raise ValueError(msg) from error
            if not np.isfinite(x) or not np.isfinite(y):
                msg = f"Non-finite position in {path}, row {row_number}"
                raise ValueError(msg)
            if time in positions_by_time:
                msg = f"Duplicate timestep {time} in {path}"
                raise ValueError(msg)
            positions_by_time[time] = (building, floor, x, y)

    return AgentTrack(
        name=f"{match.group('agent_type')}_{match.group('agent_id')}",
        positions_by_time=positions_by_time,
    )


def load_trajectories(input_path: Path) -> list[AgentTrack]:
    """Load trajectory CSV files from a directory or a single CSV."""
    paths = (
        [input_path]
        if input_path.is_file() and input_path.suffix.lower() == ".csv"
        else sorted(input_path.glob("agent_*_trajectory.csv"))
        if input_path.is_dir()
        else []
    )
    if not paths:
        msg = f"No agent trajectory CSV files found at {input_path}"
        raise FileNotFoundError(msg)
    return [_read_track(path) for path in paths]


def _sampling_interval(times: list[int]) -> int:
    """Return the regular simulation-time interval represented by the CSVs."""
    if len(times) < 2:
        return 1
    intervals = np.diff(times)
    if np.any(intervals <= 0) or not np.all(intervals == intervals[0]):
        msg = "Trajectory timesteps must be regularly spaced and strictly increasing"
        raise ValueError(msg)
    return int(intervals[0])


def detect_contacts(
    tracks: list[AgentTrack], distance_threshold: float
) -> tuple[list[ContactObservation], int]:
    """Find contacts between agents sharing a building and floor."""
    if distance_threshold < 0 or not np.isfinite(distance_threshold):
        msg = "Distance threshold must be a finite, non-negative value"
        raise ValueError(msg)

    all_times = sorted({time for track in tracks for time in track.positions_by_time})
    interval = _sampling_interval(all_times)
    observations: list[ContactObservation] = []
    for index, track_a in enumerate(tracks):
        for track_b in tracks[index + 1 :]:
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


def _build_episodes(
    observations: list[ContactObservation], interval: int
) -> list[ContactEpisode]:
    """Group consecutive contact observations into episodes."""
    by_pair: dict[tuple[str, str], list[int]] = defaultdict(list)
    for observation in observations:
        by_pair[(observation.agent_a, observation.agent_b)].append(observation.time)

    episodes: list[ContactEpisode] = []
    for (agent_a, agent_b), pair_times in sorted(by_pair.items()):
        times = sorted(set(pair_times))
        start = previous = times[0]
        count = 1
        for time in times[1:]:
            if time != previous + interval:
                episodes.append(
                    ContactEpisode(
                        agent_a, agent_b, start, previous, count * interval, count
                    )
                )
                start = time
                count = 0
            previous = time
            count += 1
        episodes.append(
            ContactEpisode(agent_a, agent_b, start, previous, count * interval, count)
        )
    return episodes


def _write_csv(
    path: Path, fieldnames: list[str], rows: list[dict[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_outputs(
    observations: list[ContactObservation],
    episodes: list[ContactEpisode],
    times: list[int],
    output_dir: Path,
    bins: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "contact_observations.csv",
        [
            "time",
            "agent_a",
            "agent_b",
            "distance",
            "building",
            "floor",
            "midpoint_x",
            "midpoint_y",
        ],
        [
            {
                "time": item.time,
                "agent_a": item.agent_a,
                "agent_b": item.agent_b,
                "distance": item.distance,
                "building": item.building,
                "floor": item.floor,
                "midpoint_x": item.midpoint_x,
                "midpoint_y": item.midpoint_y,
            }
            for item in observations
        ],
    )
    _write_csv(
        output_dir / "contact_episodes.csv",
        ["agent_a", "agent_b", "start_time", "end_time", "duration", "observations"],
        [
            {
                "agent_a": item.agent_a,
                "agent_b": item.agent_b,
                "start_time": item.start_time,
                "end_time": item.end_time,
                "duration": item.duration,
                "observations": item.observations,
            }
            for item in episodes
        ],
    )

    starts_by_time: dict[int, int] = defaultdict(int)
    for episode in episodes:
        starts_by_time[episode.start_time] += 1
    _write_csv(
        output_dir / "contact_timeseries.csv",
        ["time", "active_contacts", "new_episodes"],
        [
            {
                "time": time,
                "active_contacts": sum(item.time == time for item in observations),
                "new_episodes": starts_by_time[time],
            }
            for time in times
        ],
    )

    pair_totals: dict[tuple[str, str], list[ContactEpisode]] = defaultdict(list)
    for episode in episodes:
        pair_totals[(episode.agent_a, episode.agent_b)].append(episode)
    _write_csv(
        output_dir / "contact_pair_summary.csv",
        ["agent_a", "agent_b", "episodes", "total_duration", "observations"],
        [
            {
                "agent_a": agent_a,
                "agent_b": agent_b,
                "episodes": len(pair_episodes),
                "total_duration": sum(item.duration for item in pair_episodes),
                "observations": sum(item.observations for item in pair_episodes),
            }
            for (agent_a, agent_b), pair_episodes in sorted(pair_totals.items())
        ],
    )

    figure, axis = plt.subplots()
    if times:
        active_counts = [
            sum(item.time == time for item in observations) for time in times
        ]
        episode_counts = [starts_by_time[time] for time in times]
        axis.step(times, active_counts, where="post", label="Active agent pairs")
        axis.step(times, episode_counts, where="post", label="New contact episodes")
        axis.legend()
    else:
        axis.text(0.5, 0.5, "No contacts detected", ha="center", va="center")
    axis.set(
        xlabel="Simulation timestep",
        ylabel="Count",
        title="Agent contacts over time",
    )
    figure.tight_layout()
    figure.savefig(output_dir / "contact_timeseries.png")
    plt.close(figure)

    by_space: dict[tuple[int, int], list[ContactObservation]] = defaultdict(list)
    for item in observations:
        by_space[(item.building, item.floor)].append(item)
    if not by_space:
        figure, axis = plt.subplots()
        axis.text(0.5, 0.5, "No contacts detected", ha="center", va="center")
        axis.set(
            title="Contact location heatmap",
            xlabel="X position",
            ylabel="Y position",
        )
        figure.tight_layout()
        figure.savefig(output_dir / "contact_heatmap.png")
        plt.close(figure)
    for (building, floor), items in sorted(by_space.items()):
        figure, axis = plt.subplots()
        histogram = axis.hist2d(
            [item.midpoint_x for item in items],
            [item.midpoint_y for item in items],
            bins=bins,
            cmap="hot",
        )
        figure.colorbar(histogram[3], ax=axis, label="Contact observations")
        axis.set(
            xlabel="X position",
            ylabel="Y position",
            title=f"Contact locations (building {building}, floor {floor})",
            aspect="equal",
        )
        figure.tight_layout()
        figure.savefig(
            output_dir / f"contact_heatmap_building_{building}_floor_{floor}.png"
        )
        plt.close(figure)


def analyze_contacts(
    input_path: Path,
    output_dir: Path,
    *,
    distance_threshold: float = 0.1,
    bins: int = 50,
) -> tuple[list[ContactObservation], list[ContactEpisode]]:
    """Analyse recorded trajectories and write contact data and plots."""
    if bins < 1:
        msg = "Heatmap bins must be a positive integer"
        raise ValueError(msg)
    tracks = load_trajectories(input_path)
    logger.info("Loaded %s agent trajectories from %s", len(tracks), input_path)
    observations, interval = detect_contacts(tracks, distance_threshold)
    logger.info(
        "Detected %s contact observations with distance threshold %.3f",
        len(observations),
        distance_threshold,
    )
    episodes = _build_episodes(observations, interval)
    logger.info("Grouped into %s contact episodes", len(episodes))
    all_times = sorted({time for track in tracks for time in track.positions_by_time})
    logger.info("Writing outputs to %s", output_dir)
    _write_outputs(observations, episodes, all_times, output_dir, bins)
    logger.info("Contact analysis complete")
    return observations, episodes


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Analyse agent contacts from recorded trajectory CSVs."
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path("simulation_outputs"),
        help="trajectory CSV file or directory (default: simulation_outputs)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("simulation_outputs/contact_analysis"),
        help="directory for CSV summaries and plots",
    )
    parser.add_argument(
        "--distance-threshold",
        type=float,
        default=0.1,
        help="maximum distance in metres for contact (default: 0.1)",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=50,
        help="number of spatial bins per axis in heatmaps (default: 50)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the contact analysis command-line interface."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args(argv)
    try:
        observations, episodes = analyze_contacts(
            args.input,
            args.output,
            distance_threshold=args.distance_threshold,
            bins=args.bins,
        )
    except (FileNotFoundError, ValueError) as error:
        build_parser().error(str(error))
    logger.info(
        "Analyzed %s contact observations across %s episodes; outputs saved to %s",
        len(observations),
        len(episodes),
        args.output,
    )


if __name__ == "__main__":
    main()
