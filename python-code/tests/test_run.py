"""Tests for the simulation run helpers."""

from pathlib import Path
from typing import Any

import pytest

from amr_hub_abm import run
from amr_hub_abm.run import run_and_analyse_contacts, run_steps


class FakeSimulation:
    """Minimal stand-in for Simulation that records calls."""

    def __init__(self, total_time: int) -> None:
        """Create a fake simulation lasting ``total_time`` steps."""
        self.time = 0
        self.total_simulation_time = total_time
        self.space: list[Any] = []
        self.live_plot_times: list[int] = []
        self.final_record_time: int | None = None

    def step(self, **_kwargs: object) -> None:
        """Advance one timestep."""
        self.time += 1

    def record_current_state(self) -> None:
        """Record the time at which the final state was captured."""
        self.final_record_time = self.time

    def plot_live(self, _figures: list, *, trajectory: bool) -> None:
        """Record when live plotting is requested."""
        assert trajectory is False
        self.live_plot_times.append(self.time)

    def record_agent_states(self, path: Path) -> None:
        """Write two coincident agents' trajectories next to ``path``."""
        for filename in (
            "agent_healthcare_worker_1_trajectory.csv",
            "agent_patient_2_trajectory.csv",
        ):
            (path.parent / filename).write_text(
                "time,building,floor,x,y\n0,1,0,0.0,0.0\n1,1,0,0.0,0.0\n",
                encoding="utf-8",
            )


def test_run_steps_plots_live_every_hundred_steps() -> None:
    """Live plotting happens every 100 steps when figures are supplied."""
    simulation = FakeSimulation(200)

    run_steps(simulation, None, record=False, figures=[])  # type: ignore[arg-type]

    assert simulation.time == 200
    assert simulation.live_plot_times == [100, 200]


def test_run_steps_records_final_state_only_when_recording() -> None:
    """The state after the last step is recorded when ``record`` is set."""
    recorded = FakeSimulation(3)
    run_steps(recorded, None, record=True)  # type: ignore[arg-type]
    assert recorded.final_record_time == 3

    unrecorded = FakeSimulation(3)
    run_steps(unrecorded, None, record=False)  # type: ignore[arg-type]
    assert unrecorded.final_record_time is None


def test_run_and_analyse_contacts_writes_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run helper records trajectories and analyses their contacts."""
    simulation = FakeSimulation(2)
    monkeypatch.setattr(run, "create_simulation", lambda *_a, **_k: simulation)

    observations, episodes = run_and_analyse_contacts(
        tmp_path / "out", heatmap_format="svg"
    )

    assert len(observations) == 2
    assert len(episodes) == 1
    assert (tmp_path / "out" / "contact_analysis" / "contact_network.svg").exists()
