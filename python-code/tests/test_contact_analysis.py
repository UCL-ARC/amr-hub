"""Tests for recorded trajectory contact analysis."""

import csv
from pathlib import Path

import numpy as np
import pytest

from amr_hub_abm.contact_analysis import (
    AgentTrack,
    ContactObservation,
    analyze_contacts,
    detect_contacts,
    load_trajectories,
)
from amr_hub_abm.spatial.building import Building
from amr_hub_abm.spatial.floor import Floor
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.spatial.wall import Wall

FIELDS = ["time", "building", "floor", "x", "y", "heading", "infection_status"]


def write_track(
    directory: Path,
    filename: str,
    positions: list[tuple[int, int, int, float, float]],
) -> Path:
    """Write a small trajectory fixture."""
    path = directory / filename
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        for time, building, floor, x, y in positions:
            writer.writerow(
                {
                    "time": time,
                    "building": building,
                    "floor": floor,
                    "x": x,
                    "y": y,
                    "heading": 0,
                    "infection_status": 0,
                }
            )
    return path


def test_detect_contacts_uses_threshold_and_requires_same_floor(
    tmp_path: Path,
) -> None:
    """Only same-floor pairs within the inclusive distance threshold contact."""
    first = write_track(
        tmp_path,
        "agent_healthcare_worker_1_trajectory.csv",
        [(0, 1, 0, 0.0, 0.0)],
    )
    write_track(
        tmp_path,
        "agent_patient_2_trajectory.csv",
        [(0, 1, 0, 0.1, 0.0)],
    )
    write_track(
        tmp_path,
        "agent_patient_3_trajectory.csv",
        [(0, 1, 1, 0.0, 0.0)],
    )

    observations, interval = detect_contacts(load_trajectories(tmp_path), 0.1)

    assert interval == 1
    assert len(observations) == 1
    assert observations[0].distance == pytest.approx(0.1)
    assert observations[0].midpoint_x == pytest.approx(0.05)
    assert observations[0].building == 1
    assert observations[0].floor == 0
    assert first.exists()


def test_detect_contacts_excludes_agents_in_different_rooms(tmp_path: Path) -> None:
    """Nearby agents in separate rooms are not considered to be in contact."""
    left = Room(
        room_id=1,
        name="Left",
        building="Building A",
        floor=0,
        walls=[
            Wall((0, 0), (1, 0)),
            Wall((1, 0), (1, 1)),
            Wall((1, 1), (0, 1)),
            Wall((0, 1), (0, 0)),
        ],
        contents=[],
        doors=[],
        rng_generator=np.random.default_rng(),
    )
    right = Room(
        room_id=2,
        name="Right",
        building="Building A",
        floor=0,
        walls=[
            Wall((1, 0), (2, 0)),
            Wall((2, 0), (2, 1)),
            Wall((2, 1), (1, 1)),
            Wall((1, 1), (1, 0)),
        ],
        contents=[],
        doors=[],
        rng_generator=np.random.default_rng(),
    )
    buildings = [Building(name="Building A", floors=[Floor(0, [left, right])])]
    building_id = hash("Building A") % 128
    write_track(
        tmp_path,
        "agent_healthcare_worker_1_trajectory.csv",
        [(0, building_id, 0, 0.95, 0.5), (1, building_id, 0, 0.8, 0.5)],
    )
    write_track(
        tmp_path,
        "agent_patient_2_trajectory.csv",
        [(0, building_id, 0, 1.05, 0.5), (1, building_id, 0, 0.85, 0.5)],
    )

    observations, _ = detect_contacts(load_trajectories(tmp_path), 0.2, buildings)

    assert [observation.time for observation in observations] == [1]


def test_detect_contacts_matches_pairwise_results_across_grid_edges() -> None:
    """Spatial indexing preserves pairwise results across cells and space groups."""
    rng = np.random.default_rng(42)
    tracks = [
        AgentTrack(
            name=f"patient_{agent_id}",
            positions_by_time={
                time: (
                    int(rng.integers(0, 2)),
                    int(rng.integers(0, 2)),
                    float(rng.uniform(-2, 2)),
                    float(rng.uniform(-2, 2)),
                )
                for time in range(5)
                if rng.random() > 0.15
            },
        )
        for agent_id in range(12)
    ]
    # Force contacts on opposite sides of a cell boundary and exact threshold.
    tracks[0].positions_by_time[0] = (0, 0, -0.01, 0.0)
    tracks[1].positions_by_time[0] = (0, 0, 0.24, 0.0)
    threshold = 0.25

    expected: list[ContactObservation] = []
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
                if distance <= threshold:
                    agent_a, agent_b = sorted((track_a.name, track_b.name))
                    expected.append(
                        ContactObservation(
                            time,
                            agent_a,
                            agent_b,
                            distance,
                            building_a,
                            floor_a,
                            (x_a + x_b) / 2,
                            (y_a + y_b) / 2,
                        )
                    )
    expected.sort(key=lambda item: (item.time, item.agent_a, item.agent_b))

    actual, interval = detect_contacts(tracks, threshold)

    assert interval == 1
    assert actual == expected


def test_detect_contacts_zero_threshold_matches_identical_positions() -> None:
    """A zero threshold matches only agents at exactly coincident coordinates."""
    tracks = [
        AgentTrack("patient_1", {0: (1, 0, 0.0, 0.0)}),
        AgentTrack("patient_2", {0: (1, 0, 0.0, 0.0)}),
        AgentTrack("patient_3", {0: (1, 0, 1e-12, 0.0)}),
    ]

    observations, _ = detect_contacts(tracks, 0.0)

    assert [(item.agent_a, item.agent_b, item.distance) for item in observations] == [
        ("patient_1", "patient_2", 0.0)
    ]


def test_analyze_contacts_writes_episode_summaries_and_plots(tmp_path: Path) -> None:
    """Write observations, episode durations, time series, and heatmaps."""
    input_dir = tmp_path / "trajectories"
    output_dir = tmp_path / "analysis"
    input_dir.mkdir()
    first = [(time, 1, 0, 0.0 if time != 2 else 1.0, 0.0) for time in range(5)]
    second = [(time, 1, 0, 0.05, 0.0) for time in range(5)]
    write_track(input_dir, "agent_healthcare_worker_1_trajectory.csv", first)
    write_track(input_dir, "agent_patient_2_trajectory.csv", second)

    observations, episodes = analyze_contacts(input_dir, output_dir)

    assert len(observations) == 4
    assert [
        (episode.start_time, episode.end_time, episode.duration) for episode in episodes
    ] == [(0, 1, 2), (3, 4, 2)]
    with (output_dir / "contact_timeseries.csv").open(
        newline="", encoding="utf-8"
    ) as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert [int(row["active_contacts"]) for row in rows] == [1, 1, 0, 1, 1]
    assert [int(row["new_episodes"]) for row in rows] == [1, 0, 0, 1, 0]

    with (output_dir / "contact_pair_summary.csv").open(
        newline="", encoding="utf-8"
    ) as csv_file:
        pair_summary = list(csv.DictReader(csv_file))
    assert pair_summary[0]["episodes"] == "2"
    assert pair_summary[0]["total_duration"] == "4"
    assert pair_summary[0]["observations"] == "4"
    assert (output_dir / "contact_observations.csv").exists()
    assert (output_dir / "contact_episodes.csv").exists()
    assert (output_dir / "contact_timeseries.png").exists()
    assert (output_dir / "contact_heatmap_building_1_floor_0.png").exists()
    for kind in ("episodes", "time"):
        for grouping in ("agent_pair", "agent_type_pair"):
            assert (output_dir / f"contact_pie_{kind}_by_{grouping}.png").exists()


def test_analyze_contacts_with_no_contacts_writes_zero_timeseries(
    tmp_path: Path,
) -> None:
    """Write zero counts and a placeholder heatmap when no pairs contact."""
    input_dir = tmp_path / "trajectories"
    output_dir = tmp_path / "analysis"
    input_dir.mkdir()
    write_track(
        input_dir,
        "agent_healthcare_worker_1_trajectory.csv",
        [(0, 1, 0, 0.0, 0.0), (1, 1, 0, 0.0, 0.0)],
    )
    write_track(
        input_dir,
        "agent_patient_2_trajectory.csv",
        [(0, 1, 0, 1.0, 0.0), (1, 1, 0, 1.0, 0.0)],
    )

    observations, episodes = analyze_contacts(input_dir, output_dir)

    assert observations == []
    assert episodes == []
    with (output_dir / "contact_timeseries.csv").open(
        newline="", encoding="utf-8"
    ) as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert [row["active_contacts"] for row in rows] == ["0", "0"]
    assert (output_dir / "contact_heatmap.png").exists()
    assert (output_dir / "contact_pie_time_by_agent_type_pair.png").exists()


def test_detect_contacts_rejects_irregular_sample_times(tmp_path: Path) -> None:
    """Reject irregular sample intervals to keep duration calculations valid."""
    write_track(
        tmp_path,
        "agent_healthcare_worker_1_trajectory.csv",
        [(0, 1, 0, 0.0, 0.0), (1, 1, 0, 0.0, 0.0), (3, 1, 0, 0.0, 0.0)],
    )

    with pytest.raises(ValueError, match="regularly spaced"):
        detect_contacts(load_trajectories(tmp_path), 0.1)
