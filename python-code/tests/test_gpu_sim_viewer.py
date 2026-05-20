"""Unit tests for the Dash visualization and map layout render pipeline."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from amr_hub_abm.gpu_sim_viewer import app, update_map


def test_dash_layout_and_map_generation() -> None:
    """Verify Dash UI component states and map layout updates render correctly."""
    # 1. Assemble localized dataframes
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

    # 2. Build a mock dictionary matching the new get_simulation_data() return type
    mock_sim_data = {
        "df": mock_df,
        "df_events": mock_events,
        "times": [500],
        "max_time": 500,
        "event_options": [],
        "wall_x": [],
        "wall_y": [],
        "room_x": [],
        "room_y": [],
        "room_names": [],
        "beds": np.array([]),
        "door_coords": {},
    }

    # 3. Intercept data retrieval layer to supply our fixed dictionary instantly
    with patch(
        "amr_hub_abm.gpu_sim_viewer.get_simulation_data",
        return_value=mock_sim_data,
    ):
        # 4. Verify Dash layout generates successfully (handling the callable layout)
        # Because we used `app.layout = serve_layout`, it is now a function
        layout = app.layout() if callable(app.layout) else app.layout
        assert layout is not None
        # Convert the component tree to a string to check for our specific ID
        assert "live-map" in str(layout)

        # 5. Confirm visualizations assembled properly via the callback function
        fig, time_str = update_map(current_time=500)

        assert isinstance(fig, go.Figure)
        assert "Time: 500s" in time_str
