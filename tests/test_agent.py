import numpy as np
from unittest.mock import MagicMock

from amr_hub_abm.agent import Agent, AgentType, InfectionStatus, ROLE_COLOUR_MAP
from amr_hub_abm.location import Location


def test_plot_agent_with_tags() -> None:
    """Test plotting an agent with tags also calls ax.text."""
    agent = Agent(
        idx=8,
        agent_type=AgentType.HEALTHCARE_WORKER,
        infection_status=InfectionStatus.EXPOSED,
        location=Location(x=0.5, y=0.25, floor=1, building="Hospital"),
        heading_rad=0.0,
        space=[],
        rng_generator=np.random.default_rng(),
    )
    ax = MagicMock()

    agent.plot_agent(ax=ax, show_tags=True)

    # Check that the plot method was called once with the correct arguments
    ax.plot.assert_called_once_with(
        agent.location.x,
        agent.location.y,
        marker="o",
        markersize=5,
        color=ROLE_COLOUR_MAP[agent.agent_type],
    )

    # Check that the text method was called once with the correct arguments
    ax.text.assert_called_once_with(
        agent.location.x,
        agent.location.y,
        f"ID: {agent.idx}, Type: {agent.agent_type}",
        fontsize=8,
        ha="center",
        va="bottom",
        color="black",
    )
