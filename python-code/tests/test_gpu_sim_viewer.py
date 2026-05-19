"""Unit tests for the Dash visualization and map layout render pipeline."""

from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go

from amr_hub_abm.gpu_sim_viewer import app, update_map


def test_dash_layout_and_map_generation() -> None:
    """Verify Dash UI component states and map layout updates render correctly."""
    # Inline mock context to protect global dataset import calls
    with (
        patch("pandas.read_csv"),
        patch("numpy.load"),
    ):
        # 1. Verify Dash layout has loaded essential layout IDs
        assert app.layout is not None
        assert "live-map" in app.layout

    # 2. Mock out dataframes to simulate runtime visual updates
    mock_df = pd.DataFrame(
        [
            {
                "time": 500,
                "agent_id": "A1",
                "pos_x": 10.0,
                "pos_y": 15.0,
                "infection_status": 0,
            }
        ]
    )
    mock_events = pd.DataFrame(
        columns=["time", "infector", "infectee", "pos_x", "pos_y"]
    )

    # Patch the state maps of the visualizer module directly
    with (
        patch("amr_hub_abm.gpu_sim_viewer.df", mock_df),
        patch("amr_hub_abm.gpu_sim_viewer.df_events", mock_events),
        patch("amr_hub_abm.gpu_sim_viewer.times", [500]),
    ):
        # 3. Call the map updater callback function
        fig, time_str = update_map(current_time=500)

        # 4. Confirm visualizations assembled properly
        assert isinstance(fig, go.Figure)
        assert "Time: 500s" in time_str
