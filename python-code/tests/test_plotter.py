"""Tests for the agent plotter module."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.agent.enums import ROLE_COLOUR_MAP, AgentType, InfectionStatus
from amr_hub_abm.agent.plotter import plot_agent, plot_trajectory
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.space.location import Location
from amr_hub_abm.task.task import (
    Task,
    TaskAttendPatient,
    TaskPriority,
    TaskProgress,
    TaskWorkstation,
)


@pytest.fixture
def sample_agent() -> Agent:
    """Create a sample agent for plotter tests."""
    return Agent(
        idx=10,
        agent_type=AgentType.HEALTHCARE_WORKER,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(x=1.0, y=2.0, floor=1, building="Hospital"),
        heading_rad=0.0,
        rooms=[],
        rng_generator=np.random.default_rng(42),
    )


@pytest.fixture
def patient_agent() -> Agent:
    """Create a patient agent for attend-patient task labels."""
    return Agent(
        idx=99,
        agent_type=AgentType.PATIENT,
        infection_status=InfectionStatus.EXPOSED,
        location=Location(x=2.0, y=3.0, floor=1, building="Hospital"),
        heading_rad=0.0,
        rooms=[],
        rng_generator=np.random.default_rng(42),
    )


def test_plot_agent_without_tags(sample_agent: Agent) -> None:
    """Test plotting an agent without tags calls only the inner marker plot."""
    ax = MagicMock()

    plot_agent(agent=sample_agent, ax=ax, show_tags=False)

    ax.plot.assert_called_once_with(
        sample_agent.location.x,
        sample_agent.location.y,
        marker="o",
        markersize=5,
        color=ROLE_COLOUR_MAP[sample_agent.agent_type],
    )
    ax.text.assert_not_called()


def test_plot_agent_with_in_progress_attend_patient_task(
    sample_agent: Agent, patient_agent: Agent
) -> None:
    """Test plotting an agent with an in-progress attend-patient label."""
    sample_agent.infection_status = InfectionStatus.INFECTED
    sample_agent.tasks = [
        TaskAttendPatient(
            time_needed=15,
            time_due=30,
            patient=patient_agent,
            progress=TaskProgress.IN_PROGRESS,
        )
    ]
    ax = MagicMock()

    plot_agent(agent=sample_agent, ax=ax, show_tags=True)

    assert ax.plot.call_count == 2
    ax.plot.assert_any_call(
        sample_agent.location.x,
        sample_agent.location.y,
        marker="o",
        markersize=12,
        markerfacecolor="none",
        markeredgecolor="darkred",
        markeredgewidth=2,
        zorder=2,
    )
    ax.plot.assert_any_call(
        sample_agent.location.x,
        sample_agent.location.y,
        marker="o",
        markersize=5,
        color=ROLE_COLOUR_MAP[sample_agent.agent_type],
    )
    ax.text.assert_called_once_with(
        sample_agent.location.x + 0.1,
        sample_agent.location.y + 0.05,
        "Healthcare Worker 10\n(infected)\n[doing: attend_patient → patient 99]",
        fontsize=7,
        ha="left",
        va="bottom",
    )


def test_plot_agent_prefers_moving_task_over_next_upcoming(sample_agent: Agent) -> None:
    """Test plotting prefers a moving task over later task candidates."""
    moving_task = TaskWorkstation(
        time_needed=5,
        time_due=20,
        workstation_location=Location(x=4.0, y=4.0, floor=1, building="Hospital"),
        progress=TaskProgress.MOVING_TO_LOCATION,
    )
    next_task = Task(
        time_needed=5,
        time_due=10,
        progress=TaskProgress.NOT_STARTED,
    )
    sample_agent.tasks = [next_task, moving_task]
    ax = MagicMock()

    plot_agent(agent=sample_agent, ax=ax, show_tags=True)

    ax.text.assert_called_once_with(
        sample_agent.location.x + 0.1,
        sample_agent.location.y + 0.05,
        "Healthcare Worker 10\n[moving to: workstation]",
        fontsize=7,
        ha="left",
        va="bottom",
    )


def test_plot_agent_selects_next_upcoming_task_by_due_and_priority(
    sample_agent: Agent,
) -> None:
    """Test plotting selects the next not-started task using due time and priority."""
    later_task = Task(
        time_needed=5,
        time_due=12,
        progress=TaskProgress.NOT_STARTED,
    )
    higher_priority_same_due = Task(
        time_needed=5,
        time_due=8,
        progress=TaskProgress.NOT_STARTED,
        priority=TaskPriority.HIGH,
    )
    earlier_priority_same_due = Task(
        time_needed=5,
        time_due=8,
        progress=TaskProgress.NOT_STARTED,
        priority=TaskPriority.LOW,
    )
    sample_agent.tasks = [
        later_task,
        higher_priority_same_due,
        earlier_priority_same_due,
    ]
    ax = MagicMock()

    plot_agent(agent=sample_agent, ax=ax, show_tags=True)

    ax.text.assert_called_once_with(
        sample_agent.location.x + 0.1,
        sample_agent.location.y + 0.05,
        "Healthcare Worker 10\n[next: generic]",
        fontsize=7,
        ha="left",
        va="bottom",
    )


def test_plot_trajectory_raises_for_zero_length(sample_agent: Agent) -> None:
    """Test plotting a trajectory raises when recording was not enabled."""
    ax = MagicMock()

    with pytest.raises(SimulationModeError) as exc_info:
        plot_trajectory(sample_agent, ax)

    assert "trajectory_length of 0" in str(exc_info.value)


def test_plot_trajectory_returns_without_plotting_for_non_positive_end() -> None:
    """Test plotting a trajectory does nothing when current_time is zero."""
    agent = Agent(
        idx=11,
        agent_type=AgentType.GENERIC,
        infection_status=InfectionStatus.SUSCEPTIBLE,
        location=Location(x=0.0, y=0.0, floor=1, building="Hospital"),
        heading_rad=0.0,
        rooms=[],
        rng_generator=np.random.default_rng(42),
        trajectory_length=3,
    )
    ax = MagicMock()

    plot_trajectory(agent, ax, current_time=0)

    ax.plot.assert_not_called()


def test_plot_trajectory_plots_agent_positions() -> None:
    """Test plotting a trajectory uses the stored x and y positions."""
    agent = Agent(
        idx=12,
        agent_type=AgentType.PATIENT,
        infection_status=InfectionStatus.RECOVERED,
        location=Location(x=0.0, y=0.0, floor=1, building="Hospital"),
        heading_rad=0.0,
        rooms=[],
        rng_generator=np.random.default_rng(42),
        trajectory_length=3,
    )
    agent.trajectory.position[:, 0] = np.array([1.0, 2.0, 3.0])
    agent.trajectory.position[:, 1] = np.array([1.5, 2.5, 3.5])
    ax = MagicMock()

    plot_trajectory(agent, ax)

    args, kwargs = ax.plot.call_args
    np.testing.assert_array_equal(args[0], np.array([1.0, 2.0, 3.0]))
    np.testing.assert_array_equal(args[1], np.array([1.5, 2.5, 3.5]))
    assert kwargs == {
        "linestyle": "-",
        "linewidth": 1.5,
        "color": ROLE_COLOUR_MAP[agent.agent_type],
        "alpha": 0.7,
    }
