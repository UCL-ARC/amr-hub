"""
AMR-Hub Dashboard and Simulation Viewer.

UCLARC: Nicolin Govender.
Integrates existing logic (Tasks/Agents) with GPU Physics (CUDA Warp).
Calculates HashGrid transmission, executes BVH spatial queries,
and records telemetry for the HTML dashboard.
"""

import logging
from enum import IntEnum
from functools import cache
from pathlib import Path
from typing import Any, cast

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html

# Setup standard logger
logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Config
# =============================================================================
class InfectionStatus(IntEnum):
    """Enumeration of possible agent infection statuses."""

    SUSCEPTIBLE = 0
    EXPOSED = 1
    INFECTED = 2
    RECOVERED = 3


# =============================================================================
# A & B] Lazy Load Helpers
# =============================================================================
def _resolve_duplicate_paths(df: pd.DataFrame, dup_agents: np.ndarray) -> pd.DataFrame:
    """Resolve physical paths via Nearest-Neighbor tracking."""
    logger.info("Resolving duplicate paths")
    for aid in dup_agents:
        mask = df["agent_id"] == aid
        subset: pd.DataFrame = df[mask].sort_values("time")

        last_pos: dict[str, tuple[float, float]] = {}
        resolved_ids: list[str] = []

        # Map physical paths via Nearest-Neighbor
        for _t, group in subset.groupby("time"):
            if not last_pos:
                for i, row in enumerate(group.itertuples()):
                    uid: str = f"Trk{i}"
                    last_pos[uid] = (
                        float(cast("Any", row.pos_x)),
                        float(cast("Any", row.pos_y)),
                    )
                    resolved_ids.append(uid)
            else:
                available_uids: list[str] = list(last_pos.keys())
                for row in group.itertuples():
                    best_uid: str = available_uids[0]
                    min_d: float = float("inf")

                    rx: float = float(cast("Any", row.pos_x))
                    ry: float = float(cast("Any", row.pos_y))

                    for uid in available_uids:
                        px, py = last_pos[uid]
                        d: float = (rx - px) ** 2 + (ry - py) ** 2
                        if d < min_d:
                            min_d = d
                            best_uid = uid
                    resolved_ids.append(best_uid)
                    last_pos[best_uid] = (rx, ry)
                    available_uids.remove(best_uid)

        subset["temp_id"] = resolved_ids

        # Assign A (moving track) and P (stationary track)
        track_variances: pd.Series = (
            subset.groupby("temp_id")[["pos_x", "pos_y"]].var().sum(axis=1)
        )
        hcw_trk: str = str(track_variances.idxmax())

        num: str = str(aid).replace("A", "")

        subset["final_id"] = [
            f"A{num}" if trk == hcw_trk else f"P{num}" for trk in subset["temp_id"]
        ]
        df.loc[subset.index, "agent_id"] = subset["final_id"]
    return df


# =============================================================================


# =============================================================================
def _load_telemetry(path: Path) -> tuple[pd.DataFrame, list[int], int]:
    """Load and format the agent telemetry dataframe."""
    try:
        df = pd.read_csv(str(path))
        if "status" in df.columns:
            df = df.rename(columns={"status": "infection_status"})

        # Separate Agent (A) and Patient (P) IDs
        df["agent_id"] = df["agent_id"].astype(str)
        df["agent_id"] = df["agent_id"].apply(
            lambda x: x if x.startswith("A") else f"A{x}"
        )

        dup_agents: np.ndarray = df[df.duplicated(["time", "agent_id"])][
            "agent_id"
        ].unique()
        if len(dup_agents) > 0:
            df = _resolve_duplicate_paths(df, dup_agents)

        times = sorted(df["time"].unique())
        max_time = times[-1] if times else 0
        return df, times, max_time  # noqa: TRY300

    except FileNotFoundError:
        logger.warning("Telemetry file not found. Booting with defaults.")
        return (
            pd.DataFrame(
                columns=["time", "agent_id", "pos_x", "pos_y", "infection_status"]
            ),
            [0],
            0,
        )


# =============================================================================


# =============================================================================
def _load_events(path: Path) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Load transmission events and dropdown options."""
    try:
        df_events = pd.read_csv(str(path))
        df_events = df_events.rename(
            columns={
                "source_id": "infector",
                "target_id": "infectee",
                "location_x": "pos_x",
                "location_y": "pos_y",
            }
        )

        unique_events: list[int] = sorted(df_events["time"].unique())
        if unique_events:
            options = [
                {"label": f"Transmission at t={t}s", "value": t} for t in unique_events
            ]
        else:
            options = [
                {"label": "No Transmissions Occurred", "value": 0, "disabled": True}
            ]
        return df_events, options  # noqa: TRY300

    except FileNotFoundError:
        logger.warning("Events file not found. Booting without markers.")
        return (
            pd.DataFrame(columns=["time", "infector", "infectee", "pos_x", "pos_y"]),
            [{"label": "❌ Event File Missing", "value": 0, "disabled": True}],
        )


# =============================================================================


# =============================================================================
def _load_cad_geometry(path: Path) -> dict[str, Any]:
    """Load and structure layout arrays."""
    data: dict[str, Any] = {
        "wall_x": [],
        "wall_y": [],
        "room_x": [],
        "room_y": [],
        "room_names": [],
        "beds": np.array([]),
        "door_coords": {},
    }
    try:
        geom = np.load(str(path), allow_pickle=True)

        wall_v = geom["wall_vertices"]
        wall_x, wall_y = [], []

        for i in range(0, len(wall_v), 4):
            p1 = wall_v[i]
            p2 = wall_v[i + 1]
            wall_x.extend([float(p1[0]), float(p2[0]), None])
            wall_y.extend([float(p1[1]), float(p2[1]), None])
        data["wall_x"] = wall_x
        data["wall_y"] = wall_y

        if "room_coords" in geom and "room_names" in geom:
            data["room_coords"] = geom["room_coords"]
            data["room_names"] = [str(name) for name in geom["room_names"]]
            data["room_x"] = [float(c[0]) for c in geom["room_coords"]]
            data["room_y"] = [float(c[1]) for c in geom["room_coords"]]

        if "beds" in geom:
            data["beds"] = geom["beds"]

        if "doors" in geom:
            door_coords = {}
            for i, door_pts in enumerate(geom["doors"]):
                door_coords[i + 1] = {
                    "x": [float(door_pts[0][0]), float(door_pts[1][0])],
                    "y": [float(door_pts[0][1]), float(door_pts[1][1])],
                }
            data["door_coords"] = door_coords
        return data  # noqa: TRY300

    except FileNotFoundError:
        logger.warning("CAD Geometry not found. Booting without walls.")
        return data


# =============================================================================


# =============================================================================
@cache
def get_simulation_data() -> dict[str, Any]:
    """
    Lazy load simulation telemetry, events, and geometry strictly when requested.

    Uses caching so heavy CSV and duplicate path resolution runs only once.
    """
    logger.info("Loading Simulation Results")

    # Define paths
    telemetry_path = Path("../python-code/simulation_outputs/gpu_sim_telemetry.csv")
    events_path = Path("../python-code/simulation_outputs/gpu_sim_events.csv")
    cad_path = Path("../python-code/tests/inputs/GPU_floorplan_simple_a.npz")

    # 1. Load Telemetry
    df, times, max_time = _load_telemetry(telemetry_path)

    # 2. Load Events
    df_events, event_options = _load_events(events_path)

    # 3. Load Geometry
    cad_data = _load_cad_geometry(cad_path)

    logger.info("Data and Geometry loaded/defaulted successfully!")
    return {
        "df": df,
        "times": times,
        "max_time": max_time,
        "df_events": df_events,
        "event_options": event_options,
        **cad_data,
    }


# =============================================================================

# =============================================================================
# C] Build Dash Layout (Deferred)
# =============================================================================
app = dash.Dash(__name__)
app.title = "GPU Sim Test Viewer"


def serve_layout() -> html.Div:
    """Evaluate layout components at runtime so module scope stays clean."""
    sim_data = get_simulation_data()
    times = sim_data["times"]
    max_time = sim_data["max_time"]
    event_options = sim_data["event_options"]

    slider_marks: dict[str, dict[str, Any]] = {
        str(t): {"label": str(t), "style": {"color": "#495057"}}
        for t in times
        if t % 10000 == 0 or t == max_time
    }

    layout_style: dict[str, str] = {
        "backgroundColor": "#F8F9FA",
        "color": "#212529",
        "padding": "20px",
        "fontFamily": "sans-serif",
        "minHeight": "100vh",
    }

    controls_style: dict[str, str] = {
        "display": "flex",
        "alignItems": "center",
        "gap": "20px",
        "padding": "15px",
        "backgroundColor": "#E9ECEF",
        "borderRadius": "10px",
        "border": "1px solid #DEE2E6",
    }

    btn_style: dict[str, str] = {
        "padding": "10px 20px",
        "fontSize": "16px",
        "cursor": "pointer",
        "backgroundColor": "#007BFF",
        "color": "white",
        "border": "none",
        "borderRadius": "5px",
        "fontWeight": "bold",
    }

    return html.Div(
        style=layout_style,
        children=[
            html.H2(
                "Simulation Viewer",
                style={
                    "textAlign": "center",
                    "marginBottom": "0px",
                    "color": "#212529",
                },
            ),
            dcc.Graph(id="live-map", style={"height": "750px"}),
            html.Div(
                style=controls_style,
                children=[
                    html.Button(
                        "▶ Play / Pause",
                        id="play-button",
                        n_clicks=0,
                        style=btn_style,
                    ),
                    html.Div(
                        style={"flexGrow": "1"},
                        children=[
                            dcc.Slider(
                                id="time-slider",
                                min=times[0] if times else 0,
                                max=max_time,
                                step=500,
                                marks=slider_marks,
                                value=times[0] if times else 0,
                            )
                        ],
                    ),
                    html.Div(
                        id="time-display",
                        style={
                            "fontSize": "24px",
                            "fontWeight": "bold",
                            "color": "#007BFF",
                            "minWidth": "150px",
                            "textAlign": "right",
                        },
                    ),
                    html.Div(
                        style={"minWidth": "300px"},
                        children=[
                            dcc.Dropdown(
                                id="event-dropdown",
                                options=event_options,
                                placeholder="🔍 Jump to Transmission",
                                style={"color": "#212529"},
                            )
                        ],
                    ),
                ],
            ),
            dcc.Interval(
                id="anim-interval", interval=800, n_intervals=0, disabled=True
            ),
        ],
    )


# Attach layout as a dynamic function
app.layout = serve_layout
# =============================================================================


# =============================================================================
# D] App Callbacks & Rendering Logic
# =============================================================================
@app.callback(
    Output("anim-interval", "disabled"),
    Input("play-button", "n_clicks"),
    State("anim-interval", "disabled"),
)
def toggle_play(n_clicks: int, currently_disabled: bool) -> bool:  # noqa: FBT001
    """Toggle the animation interval state between playing and paused."""
    return not currently_disabled if n_clicks > 0 else True


@app.callback(
    Output("time-slider", "value"),
    [Input("anim-interval", "n_intervals"), Input("event-dropdown", "value")],
    State("time-slider", "value"),
)
def update_time(
    _n_intervals: int, selected_event_time: int | None, current_time: int
) -> int:
    """Increment step time or jump directly to a chosen event timestamp."""
    sim_data = get_simulation_data()
    times = sim_data["times"]
    trigger: str | None = ctx.triggered_id

    if trigger == "event-dropdown" and selected_event_time is not None:
        return selected_event_time

    if not times:
        return 0

    closest_time: int = min(times, key=lambda x: abs(x - current_time))
    idx: int = times.index(closest_time)
    next_idx: int = (idx + 500) % len(times)
    return times[next_idx]


@app.callback(
    [Output("live-map", "figure"), Output("time-display", "children")],
    [Input("time-slider", "value")],
)
def update_map(current_time: int) -> tuple[go.Figure, str]:
    """Render layout geometry and agent positions for the current timestep."""
    # Pull dependencies cleanly from cache
    sim_data = get_simulation_data()
    times = sim_data["times"]
    df = sim_data["df"]
    df_events = sim_data["df_events"]
    wall_x = sim_data["wall_x"]
    wall_y = sim_data["wall_y"]
    room_x = sim_data["room_x"]
    room_y = sim_data["room_y"]
    room_names = sim_data["room_names"]
    beds = sim_data["beds"]
    door_coords = sim_data["door_coords"]

    if times:
        current_time = min(times, key=lambda x: abs(x - current_time))
    fig = go.Figure()

    # 5.1 Static Semantic Layer
    fig.add_trace(
        go.Scatter(
            x=wall_x,
            y=wall_y,
            mode="lines",
            line={"color": "#343A40", "width": 3},
            hoverinfo="skip",
            showlegend=False,
        )
    )

    font_attr: dict[str, Any] = {
        "color": "rgba(0, 0, 0, 0.15)",
        "size": 24,
        "family": "Arial Black",
    }
    fig.add_trace(
        go.Scatter(
            x=room_x,
            y=room_y,
            mode="text",
            text=room_names,
            textfont=font_attr,
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # 5.2 Dynamic Environmental Layer
    for coords in door_coords.values():
        fig.add_trace(
            go.Scatter(
                x=coords["x"],
                y=coords["y"],
                mode="lines",
                line={"color": "#28A745", "width": 4, "dash": "dot"},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    for b in beds:
        fig.add_shape(
            type="rect",
            x0=b[0],
            y0=b[1],
            x1=b[2],
            y1=b[3],
            line={"color": "#4169E1", "width": 2},
            fillcolor="rgba(65, 105, 225, 0.1)",
        )

    # 5.3 Comet Trails
    h_mask = (df["time"] <= current_time) & (df["time"] > current_time - 5000)
    history_df: pd.DataFrame = df[h_mask]
    for aid in history_df["agent_id"].unique():
        adata: pd.DataFrame = history_df[history_df["agent_id"] == aid].iloc[::50]

        if aid.startswith("P"):
            trail_color: str = "rgba(156, 39, 176, 0.4)"
        else:
            trail_color = "rgba(100, 100, 100, 0.4)"

        fig.add_trace(
            go.Scatter(
                x=adata["pos_x"],
                y=adata["pos_y"],
                mode="lines",
                line={"color": trail_color, "width": 2, "dash": "solid"},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # 5.4 Current Agent Positions
    current_df: pd.DataFrame = df[df["time"] == current_time]
    agent_colors: list[str] = []
    for aid, status in zip(
        current_df["agent_id"], current_df["infection_status"], strict=False
    ):
        if status == 2:
            agent_colors.append("#E32636")  # Red if Infected
        elif str(aid).startswith("P"):
            agent_colors.append("#9C27B0")  # Purple for Patient
        else:
            agent_colors.append("#1E90FF")  # Blue for Healthcare Worker

    marker_opts: dict[str, Any] = {
        "size": 14,
        "color": agent_colors,
        "line": {"color": "white", "width": 1.5},
    }
    font_opts: dict[str, Any] = {
        "color": "#212529",
        "size": 12,
        "family": "Arial, bold",
    }
    fig.add_trace(
        go.Scatter(
            x=current_df["pos_x"],
            y=current_df["pos_y"],
            mode="markers+text",
            marker=marker_opts,
            text=[str(aid) for aid in current_df["agent_id"]],
            textposition="top center",
            textfont=font_opts,
            hovertext=[f"Agent {aid}" for aid in current_df["agent_id"]],
            hoverinfo="text",
            showlegend=False,
        )
    )

    # 5.5 Event Markers
    current_events: pd.DataFrame = df_events[df_events["time"] == current_time]
    if not current_events.empty:
        event_texts: list[str] = [
            f"<b>⚠️ Transmission</b><br>A{row['infector']} ➔ A{row['infectee']}"
            for _, row in current_events.iterrows()
        ]
        marker_cfg: dict[str, Any] = {
            "size": 35,
            "color": "#FFC107",
            "symbol": "star-triangle-up",
            "line": {"color": "#D32F2F", "width": 3},
        }
        fig.add_trace(
            go.Scatter(
                x=current_events["pos_x"],
                y=current_events["pos_y"],
                mode="markers+text",
                marker=marker_cfg,
                text=event_texts,
                textposition="bottom center",
                textfont={"color": "#D32F2F", "size": 14, "family": "Arial, bold"},
                name="Transmission Event",
                hoverinfo="skip",
            )
        )

    # 5.6 Layout
    fig.update_layout(
        template="plotly_white",
        xaxis={
            "showgrid": False,
            "zeroline": False,
            "visible": False,
            "scaleanchor": "y",
            "scaleratio": 1,
        },
        yaxis={"showgrid": False, "zeroline": False, "visible": False},
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
    )

    return fig, f"Time: {current_time}s"


# =============================================================================

# =============================================================================
# Launch Server
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger.info("Launching Viewer backend")
    app.run(debug=True, port=8080)
