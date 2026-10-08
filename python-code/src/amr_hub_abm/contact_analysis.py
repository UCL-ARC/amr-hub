"""Analyse recorded agent trajectories for pairwise proximity contacts."""

from __future__ import annotations

import argparse
import csv
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from math import floor as math_floor
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib as mpl

mpl.use("Agg")
import networkx as nx
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.lines import Line2D

from amr_hub_abm.agent.enums import AgentType

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from amr_hub_abm.spatial.building import Building
    from amr_hub_abm.spatial.floor import Floor
    from amr_hub_abm.spatial.room import Room

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


AgentPosition = tuple[int, AgentTrack, float, float]


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


def _spatial_candidate_pairs(
    positions: list[AgentPosition], distance_threshold: float
) -> Iterator[tuple[AgentPosition, AgentPosition]]:
    """Yield only pairs whose grid cells could be within the distance threshold."""
    if distance_threshold == 0:
        coincident_positions: dict[tuple[float, float], list[AgentPosition]] = (
            defaultdict(list)
        )
        for position in positions:
            coincident_positions[(position[2], position[3])].append(position)
        for same_position in coincident_positions.values():
            yield from combinations(same_position, 2)
        return

    cells: dict[tuple[int, int], list[AgentPosition]] = defaultdict(list)
    for position in positions:
        x, y = position[2], position[3]
        cell_x, cell_y = x / distance_threshold, y / distance_threshold
        if not isfinite(cell_x) or not isfinite(cell_y):
            yield from combinations(positions, 2)
            return
        cells[(math_floor(cell_x), math_floor(cell_y))].append(position)

    for cell, cell_positions in cells.items():
        yield from combinations(cell_positions, 2)
        for offset_x in (-1, 0, 1):
            for offset_y in (-1, 0, 1):
                neighbour = (cell[0] + offset_x, cell[1] + offset_y)
                if neighbour <= cell:
                    continue
                for position_a in cell_positions:
                    for position_b in cells.get(neighbour, ()):
                        yield position_a, position_b


def detect_contacts(
    tracks: list[AgentTrack],
    distance_threshold: float,
    buildings: list[Building] | None = None,
) -> tuple[list[ContactObservation], int]:
    """Find nearby contacts, excluding pairs located in different known rooms."""
    if distance_threshold < 0 or not np.isfinite(distance_threshold):
        msg = "Distance threshold must be a finite, non-negative value"
        raise ValueError(msg)

    all_times = sorted({time for track in tracks for time in track.positions_by_time})
    interval = _sampling_interval(all_times)
    observations: list[ContactObservation] = []
    find_floor = _floor_finder(buildings) if buildings else None
    floor_cache: dict[tuple[int, int], Floor | None] = {}
    for time in all_times:
        positions_by_space: dict[tuple[int, int], list[AgentPosition]] = defaultdict(
            list
        )
        for track_index, track in enumerate(tracks):
            position = track.positions_by_time.get(time)
            if position is None:
                continue
            building, floor_number, x, y = position
            positions_by_space[(building, floor_number)].append(
                (track_index, track, x, y)
            )

        rooms_by_agent: dict[int, Room | None] = {}
        for (building, floor_number), positions in positions_by_space.items():
            for position_a, position_b in _spatial_candidate_pairs(
                positions, distance_threshold
            ):
                _, track_a, x_a, y_a = position_a
                _, track_b, x_b, y_b = position_b
                distance = float(np.hypot(x_a - x_b, y_a - y_b))
                if distance <= distance_threshold:
                    if find_floor is not None:
                        floor_key = (building, floor_number)
                        if floor_key not in floor_cache:
                            floor_cache[floor_key] = find_floor(*floor_key)
                        floor_model = floor_cache[floor_key]
                        for track_index, _track, x, y in (
                            position_a,
                            position_b,
                        ):
                            if track_index not in rooms_by_agent:
                                rooms_by_agent[track_index] = (
                                    floor_model.find_room_by_location((x, y))
                                    if floor_model
                                    else None
                                )
                        room_a = rooms_by_agent[position_a[0]]
                        room_b = rooms_by_agent[position_b[0]]
                        if (
                            room_a is not None
                            and room_b is not None
                            and room_a != room_b
                        ):
                            continue
                    agent_a, agent_b = sorted((track_a.name, track_b.name))
                    observations.append(
                        ContactObservation(
                            time=time,
                            agent_a=agent_a,
                            agent_b=agent_b,
                            distance=distance,
                            building=building,
                            floor=floor_number,
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


MAX_PIE_SLICES = 8
HEATMAP_CMAP = "plasma"
HEATMAP_ALPHA = 0.6


def _floor_finder(
    buildings: list[Building] | None,
) -> Callable[[int, int], Floor | None]:
    """
    Return a lookup from recorded (building, floor) identifiers to a ``Floor``.

    Recorded building identifiers are ``hash(name) % 128`` (see
    ``agent.output``), which is only stable within one Python process. When the
    hash does not match and there is a single building, fall back to matching
    on the floor number alone.
    """
    if not buildings:
        return lambda _building, _floor: None

    def find(building_id: int, floor_number: int) -> Floor | None:
        candidates = [
            building
            for building in buildings
            if hash(building.name) % 128 == building_id
        ]
        if not candidates and len(buildings) == 1:
            candidates = buildings
        for building in candidates:
            for floor in building.floors:
                if floor.floor_number == floor_number:
                    return floor
        return None

    return find


def _agent_type_label(agent_name: str) -> str:
    """Return a readable agent type from a track name like ``2_3``."""
    type_part = agent_name.rsplit("_", 1)[0]
    try:
        return AgentType(int(type_part)).name.replace("_", " ").title()
    except ValueError:
        return type_part


def top_slices(
    totals: dict[str, float], max_slices: int = MAX_PIE_SLICES
) -> list[tuple[str, float]]:
    """Rank categories by size, grouping the smallest into ``Other``."""
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    if len(ranked) > max_slices:
        other = sum(value for _, value in ranked[max_slices - 1 :])
        ranked = [*ranked[: max_slices - 1], ("Other", other)]
    return ranked


def contact_breakdowns(
    episodes: list[ContactEpisode],
) -> dict[str, tuple[str, dict[str, float], dict[str, float]]]:
    """
    Group contact episodes by agent pair and by agent type pair.

    Returns a mapping of grouping key to ``(label, episode_counts, durations)``.
    """

    def pair(item: ContactEpisode) -> str:
        return f"{item.agent_a} & {item.agent_b}"

    def type_pair(item: ContactEpisode) -> str:
        return " & ".join(
            sorted((_agent_type_label(item.agent_a), _agent_type_label(item.agent_b)))
        )

    groupings = {
        "agent_pair": ("agent pair", pair),
        "agent_type_pair": ("agent type pair", type_pair),
    }
    result: dict[str, tuple[str, dict[str, float], dict[str, float]]] = {}
    for key, (label, group) in groupings.items():
        episode_counts: dict[str, float] = defaultdict(float)
        durations: dict[str, float] = defaultdict(float)
        for episode in episodes:
            episode_counts[group(episode)] += 1
            durations[group(episode)] += episode.duration
        result[key] = (label, dict(episode_counts), dict(durations))
    return result


def _write_pie(
    path: Path,
    totals: dict[str, float],
    *,
    title: str,
) -> None:
    """Save a pie chart, grouping the smallest categories into ``Other``."""
    ranked = top_slices(totals)

    figure, axis = plt.subplots(figsize=(7, 6))
    if ranked and sum(value for _, value in ranked) > 0:
        axis.pie(
            [value for _, value in ranked],
            labels=[label for label, _ in ranked],
            autopct="%1.1f%%",
            startangle=90,
            counterclock=False,
        )
        axis.axis("equal")
    else:
        axis.text(0.5, 0.5, "No contacts detected", ha="center", va="center")
        axis.axis("off")
    axis.set_title(title)
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)


def _write_pie_charts(episodes: list[ContactEpisode], output_dir: Path) -> None:
    """Write pies of episode counts and contact time by agent and type pair."""
    for key, (label, episode_counts, durations) in contact_breakdowns(episodes).items():
        _write_pie(
            output_dir / f"contact_pie_episodes_by_{key}.png",
            episode_counts,
            title=f"Share of contact episodes by {label}",
        )
        _write_pie(
            output_dir / f"contact_pie_time_by_{key}.png",
            durations,
            title=f"Share of contact time by {label}",
        )


def _write_contact_network(
    observations: list[ContactObservation],
    output_dir: Path,
    image_format: str,
) -> None:
    """Save a network of agents connected by observed contacts."""
    graph = nx.Graph()
    observations_by_pair: dict[tuple[str, str], int] = defaultdict(int)
    for observation in observations:
        observations_by_pair[(observation.agent_a, observation.agent_b)] += 1
    for (agent_a, agent_b), count in sorted(observations_by_pair.items()):
        graph.add_edge(agent_a, agent_b, observations=count)

    figure, axis = plt.subplots(figsize=(10, 8))
    if graph.number_of_nodes() == 0:
        axis.text(0.5, 0.5, "No contacts detected", ha="center", va="center")
        axis.set_axis_off()
    else:
        positions = (
            nx.spring_layout(graph, seed=42, weight="observations")
            if graph.number_of_nodes() <= 150
            else nx.circular_layout(graph)
        )
        node_types = {node: _agent_type_label(node) for node in sorted(graph.nodes)}
        type_names = sorted(set(node_types.values()))
        color_map = plt.get_cmap("tab10")
        type_colors = {
            name: color_map(index % color_map.N)
            for index, name in enumerate(type_names)
        }
        weighted_degrees = dict(graph.degree(weight="observations"))
        max_degree = max(weighted_degrees.values(), default=1)
        node_sizes = [
            180 + 420 * weighted_degrees[node] / max_degree for node in graph.nodes
        ]
        max_weight = max(
            int(data["observations"]) for _, _, data in graph.edges(data=True)
        )
        edge_widths = [
            0.5 + 3 * int(data["observations"]) / max_weight
            for _, _, data in graph.edges(data=True)
        ]
        nx.draw_networkx_edges(
            graph,
            positions,
            ax=axis,
            width=edge_widths,
            alpha=0.45,
            edge_color="#526273",
        )
        nx.draw_networkx_nodes(
            graph,
            positions,
            ax=axis,
            node_size=node_sizes,
            node_color=[type_colors[node_types[node]] for node in graph.nodes],
            edgecolors="white",
            linewidths=0.8,
        )
        if graph.number_of_nodes() <= 40:
            nx.draw_networkx_labels(
                graph,
                positions,
                ax=axis,
                font_size=7,
                font_color="#17212b",
            )
        axis.legend(
            handles=[
                Line2D(
                    [0],
                    [0],
                    marker="o",
                    color="w",
                    markerfacecolor=type_colors[name],
                    label=name,
                    markersize=8,
                )
                for name in type_names
            ],
            title="Agent type",
            loc="best",
            frameon=False,
        )
        axis.set_title("Agent contact network")
        axis.text(
            0.01,
            0.01,
            "Edge width represents contact observations; node size represents "
            "weighted contacts.",
            transform=axis.transAxes,
            fontsize=8,
            color="#526273",
        )
        axis.set_axis_off()
    figure.tight_layout()
    figure.savefig(output_dir / f"contact_network.{image_format}", dpi=150)
    plt.close(figure)


def _write_csv(
    path: Path, fieldnames: list[str], rows: list[dict[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_outputs(  # noqa: PLR0913
    observations: list[ContactObservation],
    episodes: list[ContactEpisode],
    times: list[int],
    output_dir: Path,
    bins: int,
    buildings: list[Building] | None = None,
    heatmap_format: str = "png",
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
    active_by_time: dict[int, int] = defaultdict(int)
    for observation in observations:
        active_by_time[observation.time] += 1
    for episode in episodes:
        starts_by_time[episode.start_time] += 1
    _write_csv(
        output_dir / "contact_timeseries.csv",
        ["time", "active_contacts", "new_episodes"],
        [
            {
                "time": time,
                "active_contacts": active_by_time[time],
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

    _write_pie_charts(episodes, output_dir)
    _write_contact_network(observations, output_dir, heatmap_format)

    figure, axis = plt.subplots()
    if times:
        active_counts = [active_by_time[time] for time in times]
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
        figure.savefig(output_dir / f"contact_heatmap.{heatmap_format}")
        plt.close(figure)
    find_floor = _floor_finder(buildings)
    for (building, floor), items in sorted(by_space.items()):
        figure, axis = plt.subplots()
        floor_plan = find_floor(building, floor)
        if floor_plan is not None:
            floor_plan.plot(ax=axis)
        # Bin over the whole floorplan so cells are comparable and aligned with it.
        bounds = [axis.get_xlim(), axis.get_ylim()] if floor_plan is not None else None
        counts, x_edges, y_edges = np.histogram2d(
            [item.midpoint_x for item in items],
            [item.midpoint_y for item in items],
            bins=bins,
            range=bounds,
        )
        # Empty cells are masked so the floorplan stays visible beneath them.
        mesh = axis.pcolormesh(
            x_edges,
            y_edges,
            np.ma.masked_equal(counts.T, 0),
            cmap=HEATMAP_CMAP,
            alpha=HEATMAP_ALPHA,
            norm=LogNorm(vmin=1, vmax=max(float(counts.max()), 2.0)),
            zorder=3,
        )
        figure.colorbar(mesh, ax=axis, label="Contact observations")
        axis.set(
            xlabel="X position",
            ylabel="Y position",
            title=f"Contact locations (building {building}, floor {floor})",
            aspect="equal",
        )
        figure.tight_layout()
        figure.savefig(
            output_dir
            / f"contact_heatmap_building_{building}_floor_{floor}.{heatmap_format}",
            dpi=150,
        )
        plt.close(figure)


def analyze_contacts(  # noqa: PLR0913
    input_path: Path,
    output_dir: Path,
    *,
    distance_threshold: float = 0.1,
    bins: int = 50,
    buildings: list[Building] | None = None,
    heatmap_format: str = "png",
) -> tuple[list[ContactObservation], list[ContactEpisode]]:
    """
    Analyse recorded trajectories and write contact data and plots.

    If ``buildings`` is given, contacts across different rooms are excluded and
    heatmaps are overlaid on the matching floorplans. ``heatmap_format`` is the
    matplotlib image format of the heatmaps (e.g. ``svg``).
    """
    if bins < 1:
        msg = "Heatmap bins must be a positive integer"
        raise ValueError(msg)
    tracks = load_trajectories(input_path)
    logger.info("Loaded %s agent trajectories from %s", len(tracks), input_path)
    observations, interval = detect_contacts(tracks, distance_threshold, buildings)
    logger.info(
        "Detected %s contact observations with distance threshold %.3f",
        len(observations),
        distance_threshold,
    )
    episodes = _build_episodes(observations, interval)
    logger.info("Grouped into %s contact episodes", len(episodes))
    all_times = sorted({time for track in tracks for time in track.positions_by_time})
    logger.info("Writing outputs to %s", output_dir)
    _write_outputs(
        observations,
        episodes,
        all_times,
        output_dir,
        bins,
        buildings,
        heatmap_format,
    )
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
