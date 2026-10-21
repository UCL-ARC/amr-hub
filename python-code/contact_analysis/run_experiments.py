"""
Run the movement-strategy contact experiments and save raw per-run metrics.

Runs the 2x2 design (``fixed``/``deadline_paced`` x stochastic/non-stochastic)
with seeded replicates and writes one CSV row per run, split by contact pair
type (HCW-HCW, HCW-patient, patient-patient). Run from ``python-code/``::

    uv run python contact_analysis/run_experiments.py --replicates 30
"""

import argparse
import csv
import itertools
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np

from amr_hub_abm.agent.enums import AgentType
from amr_hub_abm.agent.kinematics import MovementStrategy
from amr_hub_abm.config import sim_config
from amr_hub_abm.contact_analysis import (
    AgentTrack,
    _build_episodes,
    detect_contacts,
)
from amr_hub_abm.simulation_factory import create_simulation

PAIR_TYPES = ("hcw_hcw", "hcw_patient", "patient_patient")
BASE_SEED = 20261021
CONTACT_DISTANCE = 0.1
CASES = list(
    itertools.product(
        (MovementStrategy.FIXED, MovementStrategy.DEADLINE_PACED), (True, False)
    )
)
FIELDS = [
    "strategy",
    "stochastic",
    "replicate",
    *(f"observations_{t}" for t in PAIR_TYPES),
    *(f"duration_s_{t}" for t in PAIR_TYPES),
    *(f"episodes_{t}" for t in PAIR_TYPES),
    *(f"longest_episode_s_{t}" for t in PAIR_TYPES),
]


def pair_type(agent_a: str, agent_b: str) -> str:
    """Classify a pair of track names (``<agent_type>_<id>``) by agent types."""
    hcw = str(int(AgentType.HEALTHCARE_WORKER))
    n_hcw = sum(name.split("_", 1)[0] == hcw for name in (agent_a, agent_b))
    return PAIR_TYPES[2 - n_hcw]


def run_one(
    args: tuple[MovementStrategy, bool, int, int],
) -> dict[str, str | int | float]:
    """Run one seeded simulation and return its pair-type contact metrics."""
    strategy, stochastic, replicate, step_seconds = args
    base_kinematics = sim_config.agent_kinematics
    kinematics = replace(
        base_kinematics,
        movement_strategy=strategy,
        stochasticity=base_kinematics.stochasticity if stochastic else 0.0,
    )
    config = replace(
        sim_config,
        agent_kinematics=kinematics,
        config_data={
            **sim_config.config_data,
            "length_of_timestep_in_seconds": step_seconds,
        },
    )
    seeded_rng = np.random.default_rng(BASE_SEED + replicate)
    with mock.patch("numpy.random.default_rng", return_value=seeded_rng):
        simulation = create_simulation(config)
    while simulation.time < simulation.total_simulation_time:
        simulation.step(record=True)
    simulation.record_current_state()

    tracks = []
    for agent in simulation.agents:
        record = agent.trajectory
        positions = {
            t: (
                int(record.building[t]),
                int(record.floor[t]),
                float(record.position[t, 0]),
                float(record.position[t, 1]),
            )
            for t in range(len(record.building))
        }
        tracks.append(AgentTrack(f"{int(agent.agent_type)}_{agent.idx}", positions))

    observations, interval = detect_contacts(tracks, CONTACT_DISTANCE, simulation.space)
    episodes = _build_episodes(observations, interval)

    counts: dict[str, int] = defaultdict(int)
    durations: dict[str, float] = defaultdict(float)
    episode_counts: dict[str, int] = defaultdict(int)
    longest: dict[str, float] = defaultdict(float)
    for obs in observations:
        counts[pair_type(obs.agent_a, obs.agent_b)] += 1
    for episode in episodes:
        kind = pair_type(episode.agent_a, episode.agent_b)
        seconds = episode.duration * step_seconds
        durations[kind] += seconds
        episode_counts[kind] += 1
        longest[kind] = max(longest[kind], seconds)
    row: dict[str, str | int | float] = {
        "strategy": strategy.value,
        "stochastic": int(stochastic),
        "replicate": replicate,
    }
    for t in PAIR_TYPES:
        row[f"observations_{t}"] = counts[t]
        row[f"duration_s_{t}"] = durations[t]
        row[f"episodes_{t}"] = episode_counts[t]
        row[f"longest_episode_s_{t}"] = longest[t]
    return row


def main() -> None:
    """Run all cases in parallel and write the results CSV."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicates", type=int, default=30)
    parser.add_argument("--step-seconds", type=int, default=1)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("contact_analysis/results/contact_pair_types.csv"),
    )
    args = parser.parse_args()

    jobs = [
        (strategy, stochastic, replicate, args.step_seconds)
        for strategy, stochastic in CASES
        for replicate in range(args.replicates)
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} runs to {args.output}")  # noqa: T201


if __name__ == "__main__":
    main()
