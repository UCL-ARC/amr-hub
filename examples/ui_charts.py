"""Chart helpers for the dashboard: SVG floorplans and interactive Plotly charts."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import matplotlib as mpl
import plotly.graph_objects as go
from matplotlib.figure import Figure
from ui_svg import responsive_svg
from ui_theme import COLORWAY

from amr_hub_abm.contact_analysis import top_slices

if TYPE_CHECKING:
    import pandas as pd

    from amr_hub_abm.mesa_wrapper import HospitalABM


def floorplan_svg(model: HospitalABM) -> str:
    """Render the current floorplan with agents and trajectories as scalable SVG."""
    building = model.simulation.space[0]
    n_floors = len(building.floors)
    with mpl.rc_context({"svg.fonttype": "none"}):
        figure = Figure(figsize=(7, 4.6 * n_floors), layout="constrained")
        axes = figure.subplots(nrows=n_floors, ncols=1)
        axes = axes.flatten().tolist() if hasattr(axes, "flatten") else [axes]
        building.plot_building(
            axes=axes, agents=model.simulation.agents, trajectory=True
        )
        for floor, axis in zip(building.floors, axes, strict=True):
            axis.set_title(f"Floor {floor.floor_number}", fontsize=11, loc="left")
            axis.set_aspect("equal")
        buffer = io.StringIO()
        figure.savefig(buffer, format="svg")
    return responsive_svg(buffer.getvalue())


def _base_layout(*, dark: bool, height: int, title: str) -> dict:
    return {
        "template": "plotly_dark" if dark else "plotly_white",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "colorway": COLORWAY,
        "height": height,
        "margin": {"l": 48, "r": 16, "t": 48, "b": 40},
        "title": {"text": title, "x": 0.02, "font": {"size": 15}},
        "font": {"family": "Inter, Segoe UI, Roboto, sans-serif"},
    }


def timeseries_figure(
    data: pd.DataFrame, *, dark: bool, title: str = "Contacts over time"
) -> go.Figure:
    """Build a step chart of active contacts and new contact episodes."""
    figure = go.Figure(layout=_base_layout(dark=dark, height=360, title=title))
    figure.add_scatter(
        x=data["clock"],
        y=data["active_contacts"],
        mode="lines",
        line={"shape": "hv", "width": 2},
        fill="tozeroy",
        name="Active agent pairs",
    )
    figure.add_scatter(
        x=data["clock"],
        y=data["new_episodes"],
        mode="lines",
        line={"shape": "hv", "width": 2},
        name="New contact episodes",
    )
    figure.update_layout(
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.2},
        yaxis_title="Count",
        xaxis_title="Simulation time",
    )
    return figure


def pie_figure(
    totals: dict[str, float],
    *,
    title: str,
    unit: str,
    dark: bool,
) -> go.Figure:
    """Build a donut chart for ``totals`` (small categories grouped as Other)."""
    ranked = top_slices(totals)
    figure = go.Figure(layout=_base_layout(dark=dark, height=360, title=title))
    if ranked:
        figure.add_pie(
            labels=[label for label, _ in ranked],
            values=[value for _, value in ranked],
            hole=0.55,
            sort=False,
            direction="clockwise",
            textinfo="percent",
            marker={"colors": COLORWAY, "line": {"width": 2, "color": "rgba(0,0,0,0)"}},
            hovertemplate=f"<b>%{{label}}</b><br>%{{value}} {unit}"
            "<br>%{percent}<extra></extra>",
        )
        figure.update_layout(
            legend={
                "orientation": "h",
                "x": 0.5,
                "xanchor": "center",
                "y": -0.05,
                "yanchor": "top",
            },
            margin={"l": 16, "r": 16, "t": 48, "b": 64},
        )
    else:
        figure.add_annotation(
            text="No contacts detected", showarrow=False, font={"size": 14}
        )
        figure.update_xaxes(visible=False)
        figure.update_yaxes(visible=False)
    return figure
