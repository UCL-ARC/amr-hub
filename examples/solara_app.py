"""Solara app for browser-based AMR Hub ABM visualization."""
# ruff: noqa: N802

from __future__ import annotations

import html
import io
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import solara
import solara.lab
from ui_charts import floorplan_svg, pie_figure, timeseries_figure
from ui_svg import (
    INFECTION_STATUS,
    TASK_STATUS,
    empty_state,
    icon,
    kpi_tile,
    legend,
    logo,
    qr_svg,
    responsive_svg,
    ring,
    spinner,
    status_chip,
    status_icon,
)
from ui_theme import APP_CSS, button_label

from amr_hub_abm.agent.enums import AgentType
from amr_hub_abm.config import sim_config
from amr_hub_abm.contact_analysis import ContactEpisode, contact_breakdowns
from amr_hub_abm.mesa_wrapper import HospitalABM
from amr_hub_abm.run import run_and_analyse_contacts

DOCS_URL = "https://github-pages.arc.ucl.ac.uk/amr-hub/"
FRAME_DELAY_SECONDS = 0.05

START_TIME = pd.to_datetime(str(sim_config.config_data["start_time"]))
STEP_SECONDS = int(sim_config.config_data["length_of_timestep_in_seconds"])  # type: ignore[call-overload]

# Per-session state (solara reactive variables are scoped to each browser session).
model_ref = solara.reactive(None)
tick = solara.reactive(0)
playing = solara.reactive(False)
steps_per_frame = solara.reactive(5)
selected_agent = solara.reactive(None)
contact_threshold = solara.reactive(0.1)
contact_bins = solara.reactive(50)


def get_model() -> HospitalABM:
    """Return this session's model, creating it on first use."""
    if model_ref.value is None:
        model_ref.value = HospitalABM()
    return model_ref.value


def html_block(markup: str, *, classes: list[str] | None = None) -> None:
    """Render trusted, pre-escaped HTML/SVG markup."""
    solara.HTML(unsafe_innerHTML=markup, classes=classes or [])


def clock_at(timestep: float) -> str:
    """Convert a simulation timestep into a wall-clock time string."""
    return (START_TIME + pd.to_timedelta(timestep * STEP_SECONDS, unit="s")).strftime(
        "%H:%M:%S"
    )


def format_duration(seconds: float) -> str:
    """Format seconds as a short human readable duration."""
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def agent_label(agent: object) -> str:
    """Return a readable label such as ``Healthcare Worker #1``."""
    name = agent.agent_type.name.replace("_", " ").title()  # type: ignore[attr-defined]
    return f"{name} #{agent.idx}"  # type: ignore[attr-defined]


def labelled_button_content(icon_name: str, text: str) -> list:
    """Button children combining an SVG icon with text."""
    return [
        solara.HTML(
            tag="span",
            unsafe_innerHTML=button_label(icon(icon_name, 18), text),
            style={"display": "inline-flex", "align-items": "center"},
        )
    ]


# =============================================================================
# Layout
# =============================================================================
@solara.component  # pyright: ignore[reportPrivateImportUsage]
def Layout(children: list | None = None) -> None:
    """App shell: sticky header with navigation, content area and footer."""
    route_current, routes_all = solara.use_route()
    solara.Style(APP_CSS)

    nav_icons = {"Simulation": "map", "Contact analysis": "chart"}

    with solara.Column(gap="0", style={"min-height": "100vh"}):
        with solara.Row(classes=["amr-header"]):
            html_block(
                f'<div class="amr-brand">{logo(40)}<div><h1>AMR-Hub</h1>'
                "<span>Hospital agent-based simulation</span></div></div>"
            )
            with solara.Row(classes=["amr-nav"], gap="4px"):
                for route in routes_all:
                    label = route.label or route.path
                    solara.Link(
                        solara.resolve_path(route),
                        children=[
                            solara.HTML(
                                tag="span",
                                unsafe_innerHTML=(
                                    f"{icon(nav_icons.get(label, 'map'), 18)}{label}"
                                ),
                                style={"display": "inline-flex", "gap": "8px"},
                            )
                        ],
                        classes=(
                            ["active"]
                            if route_current and route.path == route_current.path
                            else []
                        ),
                    )
            solara.Div(classes=["amr-spacer"])
            solara.lab.ThemeToggle()

        with solara.Div(classes=["amr-page"]):
            solara.Column(children=children or [], gap="0")

        html_block(
            f'<div class="amr-footer"><div class="amr-qr">{qr_svg(DOCS_URL)}</div>'
            "<div>Learn more about the AMR-Hub project<br>"
            f'<a href="{DOCS_URL}" target="_blank" rel="noopener">{DOCS_URL}</a>'
            "</div></div>"
        )


# =============================================================================
# Simulation page
# =============================================================================
def reset_model() -> None:
    """Stop playback and start a fresh simulation."""
    playing.value = False
    model_ref.value = HospitalABM()
    selected_agent.value = None
    tick.value += 1


def step_once() -> None:
    """Advance the simulation by a single step."""
    model = get_model()
    if model.simulation.time < model.simulation.total_simulation_time:
        model.step()
    tick.value += 1


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def Controls() -> None:
    """Playback controls."""
    is_playing = playing.use_value()
    tick.use_value()
    simulation = get_model().simulation
    finished = simulation.time >= simulation.total_simulation_time

    def run_loop(cancel: threading.Event) -> None:
        while not cancel.is_set() and playing.value:
            model = get_model()
            for _ in range(steps_per_frame.value):
                if model.simulation.time >= model.simulation.total_simulation_time:
                    playing.value = False
                    break
                model.step()
            tick.value += 1
            time.sleep(FRAME_DELAY_SECONDS)

    solara.use_thread(run_loop, dependencies=[is_playing])

    def toggle() -> None:
        playing.value = not playing.value

    with solara.Div(classes=["amr-card"], style={"margin-bottom": "20px"}):
        with solara.Row(
            style={"align-items": "center", "flex-wrap": "wrap"}, gap="12px"
        ):
            solara.Button(
                children=labelled_button_content(
                    "pause" if is_playing else "play",
                    "Pause" if is_playing else "Play",
                ),
                on_click=toggle,
                color="primary",
                disabled=finished,
                classes=["amr-btn"],
            )
            solara.Button(
                children=labelled_button_content("step", "Step"),
                on_click=step_once,
                disabled=is_playing or finished,
                outlined=True,
                classes=["amr-btn"],
            )
            solara.Button(
                children=labelled_button_content("reset", "Reset"),
                on_click=reset_model,
                outlined=True,
                classes=["amr-btn"],
            )
            solara.Div(classes=["amr-spacer"])
            with solara.Div(style={"min-width": "260px"}):
                solara.SliderInt(
                    "Speed (steps per frame)", value=steps_per_frame, min=1, max=50
                )
        if finished:
            html_block(
                '<div class="amr-hint" style="margin-top:4px">Simulation finished. '
                "Press <b>Reset</b> to start a new run.</div>"
            )


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def KpiStrip() -> None:
    """Headline numbers for the running simulation."""
    tick.use_value()
    simulation = get_model().simulation
    total = max(simulation.total_simulation_time, 1)
    agents = simulation.agents
    counts = {"SUSCEPTIBLE": 0, "EXPOSED": 0, "INFECTED": 0, "RECOVERED": 0}
    for agent in agents:
        counts[agent.infection_status.name] += 1
    workers = sum(a.agent_type == AgentType.HEALTHCARE_WORKER for a in agents)
    patients = sum(a.agent_type == AgentType.PATIENT for a in agents)
    tiles = [
        kpi_tile(
            "clock",
            "Simulation time",
            clock_at(simulation.time),
            f"step {simulation.time:,} of {simulation.total_simulation_time:,}",
            visual=ring(simulation.time / total, size=64, color="var(--amr-primary)"),
        ),
        kpi_tile(
            "users",
            "Agents",
            str(len(agents)),
            f"{workers} staff · {patients} patients",
        ),
        kpi_tile(
            "virus",
            "Infected",
            str(counts["INFECTED"]),
            f"{counts['RECOVERED']} recovered",
            "--amr-danger",
        ),
        kpi_tile(
            "exposed",
            "Exposed",
            str(counts["EXPOSED"]),
            f"{counts['SUSCEPTIBLE']} susceptible",
            "--amr-warn",
        ),
    ]
    html_block(f'<div class="amr-kpis">{"".join(tiles)}</div>')


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def FloorplanCard() -> None:
    """Live floorplan with agents."""
    tick_value = tick.use_value()
    model = get_model()
    svg = solara.use_memo(lambda: floorplan_svg(model), [tick_value, id(model)])
    with solara.Div(classes=["amr-card"]):
        html_block(
            "<h2>Floorplan</h2>"
            '<div class="amr-hint">Agents and their trajectories, updated live.</div>'
        )
        html_block(svg, classes=["amr-paper"])


def _fmt(value: object) -> str:
    return "–" if value is None else str(value)


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def AgentPanel() -> None:
    """Agent selector with infection status, internal state and task timeline."""
    tick.use_value()
    agents = sorted(
        get_model().simulation.agents,
        key=lambda agent: (agent.agent_type.value, agent.idx),
    )
    by_label = {agent_label(agent): agent for agent in agents}
    options = list(by_label)

    with solara.Div(classes=["amr-card"]):
        html_block("<h2>Agent inspector</h2>")
        if not options:
            html_block(empty_state("No agents", "This simulation has no agents."))
            return
        current = (
            selected_agent.value if selected_agent.value in by_label else options[0]
        )
        solara.Select(
            label="Agent",
            values=options,
            value=current,
            on_value=selected_agent.set,
            dense=True,
        )
        agent = by_label[current]
        state = agent.internal_state
        is_worker = agent.agent_type == AgentType.HEALTHCARE_WORKER
        gauges = [ring(state.hunger, "Hunger"), ring(state.toilet_need, "Toilet need")]
        if state.fatigue is not None:
            gauges.append(ring(state.fatigue, "Fatigue"))

        html_block(
            '<div class="amr-agent"><div class="amr-avatar">'
            f"{icon('nurse' if is_worker else 'bed', 24, '#fff')}</div>"
            f"<div><b>{html.escape(current)}</b><br>"
            f"{status_chip(INFECTION_STATUS, agent.infection_status.name)}</div></div>"
            f'<div class="amr-rings">{"".join(gauges)}</div>'
            '<h2 style="margin-top:14px">Tasks</h2>'
            f'<div class="amr-hint">{legend(TASK_STATUS)}</div>'
        )
        with solara.Div(classes=["amr-timeline"]):
            if not agent.tasks:
                html_block(empty_state("No tasks", "This agent has no tasks."))
            for task in agent.tasks:
                task_content = (
                    f"{status_icon(task.progress.name)}"
                    '<div><div class="amr-task-name">'
                    f"{html.escape(task.task_type.name.replace('_', ' ').title())}"
                    "</div>"
                    f'<div class="amr-task-meta">Due {_fmt(task.time_due)} · '
                    f"Start {_fmt(task.time_started)} · End "
                    f"{_fmt(task.time_completed)}</div></div>"
                    f"{status_chip(TASK_STATUS, task.progress.name)}"
                )
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML=task_content,
                    classes=["amr-task"],
                )


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def SimulationPage() -> None:
    """Animated, step-by-step simulation view."""
    get_model()
    model_ref.use_value()
    html_block(
        '<div class="amr-hero"><h2>Live simulation</h2>'
        "<p>Watch agents move around the ward and track their state in real time."
        "</p></div>"
    )
    Controls()
    KpiStrip()
    with solara.Div(classes=["amr-grid-2"]):
        FloorplanCard()
        AgentPanel()


# =============================================================================
# Contact analysis page
# =============================================================================
@solara.lab.task
def run_contact_analysis(distance_threshold: float, bins: int) -> Path:
    """Run a full headless simulation and return the contact analysis directory."""
    output_dir = Path(tempfile.mkdtemp(prefix="amr_hub_contacts_"))
    run_and_analyse_contacts(
        output_dir,
        distance_threshold=distance_threshold,
        bins=bins,
        heatmap_format="svg",
    )
    return output_dir / "contact_analysis"


@dataclass
class ContactData:
    """Parsed contact analysis outputs."""

    directory: Path
    episodes: pd.DataFrame
    timeseries: pd.DataFrame
    pairs: pd.DataFrame
    heatmaps: list[str]


def load_contact_data(directory: Path) -> ContactData:
    """Load analysis CSVs and SVG heatmaps from ``directory``."""
    timeseries = pd.read_csv(directory / "contact_timeseries.csv")
    timeseries["clock"] = START_TIME + pd.to_timedelta(
        timeseries["time"] * STEP_SECONDS, unit="s"
    )
    return ContactData(
        directory=directory,
        episodes=pd.read_csv(directory / "contact_episodes.csv"),
        timeseries=timeseries,
        pairs=pd.read_csv(directory / "contact_pair_summary.csv"),
        heatmaps=[
            responsive_svg(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("contact_heatmap*.svg"))
        ],
    )


def zip_results(directory: Path) -> bytes:
    """Zip every analysis output (CSVs and plots) for download."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.iterdir()):
            archive.write(path, path.name)
    return buffer.getvalue()


def contact_kpis(data: ContactData) -> str:
    """Summary tiles for a finished contact analysis."""
    episodes, series, pairs = data.episodes, data.timeseries, data.pairs
    total_time = episodes["duration"].sum() * STEP_SECONDS
    longest = episodes.loc[episodes["duration"].idxmax()]
    peak = series.loc[series["active_contacts"].idxmax()]
    busiest = pairs.loc[pairs["total_duration"].idxmax()]
    return "".join(
        [
            kpi_tile(
                "link",
                "Contact episodes",
                f"{len(episodes):,}",
                f"{len(pairs)} agent pairs",
            ),
            kpi_tile(
                "clock",
                "Total contact time",
                format_duration(total_time),
                "summed over all episodes",
                "--amr-accent",
            ),
            kpi_tile(
                "trophy",
                "Longest episode",
                format_duration(longest["duration"] * STEP_SECONDS),
                f"{longest['agent_a']} & {longest['agent_b']}",
                "--amr-warn",
            ),
            kpi_tile(
                "users",
                "Peak concurrent contacts",
                str(int(peak["active_contacts"])),
                f"at {peak['clock']:%H:%M:%S}",
                "--amr-danger",
            ),
            kpi_tile(
                "chart",
                "Busiest pair",
                f"{busiest['agent_a']} & {busiest['agent_b']}",
                f"{format_duration(busiest['total_duration'] * STEP_SECONDS)} together",
            ),
        ]
    )


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def ContactResults(directory: Path) -> None:
    """Summary tiles, charts, heatmaps and downloads for one analysis run."""
    dark = solara.lab.use_dark_effective()
    data = solara.use_memo(lambda: load_contact_data(directory), [directory])

    if data.episodes.empty:
        html_block(
            '<div class="amr-card">'
            + empty_state(
                "No contacts detected",
                "No agents came within the contact distance. Try a larger distance.",
            )
            + "</div>"
        )
        return

    html_block(f'<div class="amr-kpis">{contact_kpis(data)}</div>')

    breakdowns = contact_breakdowns(
        [
            ContactEpisode(
                str(row.agent_a),
                str(row.agent_b),
                int(row.start_time),
                int(row.end_time),
                int(row.duration),
                int(row.observations),
            )
            for row in data.episodes.itertuples()
        ]
    )

    with solara.Div(classes=["amr-card"]):
        with solara.lab.Tabs():
            with solara.lab.Tab("Overview", icon_name="mdi-chart-line"):
                solara.FigurePlotly(timeseries_figure(data.timeseries, dark=dark))
            with solara.lab.Tab("Who meets whom", icon_name="mdi-chart-donut"):
                with solara.Div(classes=["amr-grid-auto"]):
                    for label, counts, durations in breakdowns.values():
                        solara.FigurePlotly(
                            pie_figure(
                                counts,
                                title=f"Contact episodes by {label}",
                                unit="episodes",
                                dark=dark,
                            )
                        )
                        solara.FigurePlotly(
                            pie_figure(
                                {k: v * STEP_SECONDS for k, v in durations.items()},
                                title=f"Contact time by {label}",
                                unit="s",
                                dark=dark,
                            )
                        )
            with solara.lab.Tab("Where", icon_name="mdi-map-marker-radius"):
                html_block(
                    '<div class="amr-hint" style="margin-top:12px">Contact hotspots '
                    "overlaid on the floorplan (log colour scale).</div>"
                )
                with solara.Div(classes=["amr-grid-auto"]):
                    for svg in data.heatmaps:
                        html_block(svg, classes=["amr-paper"])
            with solara.lab.Tab("Data", icon_name="mdi-table"):
                solara.FileDownload(
                    data=lambda: zip_results(data.directory),
                    filename="contact_analysis.zip",
                    label="Download all results (zip)",
                    mime_type="application/zip",
                )
                solara.DataFrame(
                    data.pairs.sort_values("total_duration", ascending=False),
                    items_per_page=10,
                )


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def ContactAnalysisPage() -> None:
    """Separate page: single headless run with contact analysis."""
    html_block(
        '<div class="amr-hero"><h2>Contact analysis</h2>'
        "<p>Run the whole simulation once, without animation, and explore who "
        "came into contact with whom, for how long and where.</p></div>"
    )
    task = run_contact_analysis

    with solara.Div(classes=["amr-card"], style={"margin-bottom": "20px"}):
        html_block(
            "<h2>Parameters</h2>"
            '<div class="amr-hint">Two agents are in contact when they are within '
            "the distance below on the same floor.</div>"
        )
        with solara.Div(classes=["amr-grid-auto"], style={"align-items": "center"}):
            solara.SliderFloat(
                "Contact distance (metres)",
                value=contact_threshold,
                min=0.05,
                max=2.0,
                step=0.05,
            )
            solara.SliderInt(
                "Heatmap resolution (bins)",
                value=contact_bins,
                min=10,
                max=150,
                step=5,
            )
        solara.Button(
            children=labelled_button_content(
                "play", "Running…" if task.pending else "Run simulation & analyse"
            ),
            on_click=lambda: task(contact_threshold.value, contact_bins.value),
            color="primary",
            disabled=task.pending,
            classes=["amr-btn"],
        )

    if task.pending:
        html_block(
            '<div class="amr-card amr-center">'
            f"{spinner()}<div>Running the full simulation — this can take a minute…"
            "</div></div>"
        )
    elif task.error:
        solara.Error(f"Contact analysis failed: {task.exception}")
    elif task.finished:
        ContactResults(task.value)
    else:
        html_block(
            '<div class="amr-card">'
            + empty_state(
                "No results yet",
                "Choose a contact distance and run the simulation to see the analysis.",
            )
            + "</div>"
        )


routes = [
    solara.Route(path="/", component=SimulationPage, label="Simulation", layout=Layout),
    solara.Route(
        path="contact-analysis",
        component=ContactAnalysisPage,
        label="Contact analysis",
        layout=Layout,
    ),
]
