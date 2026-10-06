"""Solara app for browser-based AMR Hub ABM visualization."""
# ruff: noqa: N802

import tempfile
from pathlib import Path

import solara
import solara.lab
from matplotlib.figure import Figure
from mesa.visualization import SolaraViz
from mesa.visualization.utils import update_counter
import qrcode

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.mesa_wrapper import HospitalABM
from amr_hub_abm.run import run_and_analyse_contacts

STATUS_DICT = {
    "NOT_STARTED": "🔵",
    "MOVING_TO_LOCATION": "🚶",
    "SUSPENDED": "⏸️",
    "IN_PROGRESS": "⏳",
    "COMPLETED": "✅",
}


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def FloorplanComponent(model: HospitalABM) -> None:
    """Render the hospital floorplan with current agent positions."""
    update_counter.get()

    fig = Figure(figsize=(6, 6))

    n_floors = len(model.simulation.space[0].floors)
    axes = fig.subplots(nrows=n_floors, ncols=1)

    if hasattr(axes, "flatten"):
        axes = axes.flatten().tolist()
    else:
        axes = [axes]

    model.simulation.space[0].plot_building(
        axes=axes,
        agents=model.simulation.agents,
        trajectory=True,
    )

    fig.suptitle(
        f"Time: {model.simulation.time}/{model.simulation.total_simulation_time}"
    )

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data("https://github-pages.arc.ucl.ac.uk/amr-hub/")
    qr.make(fit=True)

    img = qr.make_image(fill="black", back_color="white")
    # Save the QR code image to a temporary file and read it back for display
    img_path = "temp_qr_code.png"
    img.save(img_path)  # pyright: ignore[reportArgumentType]

    with solara.Card(title="Floorplan", margin=0):
        solara.FigureMatplotlib(fig, format="png")
        solara.Markdown("**Scan the QR code to learn more about the AMR Hub project!**")
        solara.Image(img_path, width="200px")


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def AgentTaskTableComponent(model: HospitalABM) -> None:
    """Render the task list for a selected agent."""
    update_counter.get()

    agents_by_label: dict[str, Agent] = {
        f"{agent.agent_type.name.replace('_', ' ').title()} #{agent.idx}": agent
        for agent in sorted(
            model.simulation.agents,
            key=lambda agent: (agent.agent_type.value, agent.idx),
        )
    }
    agent_options = list(agents_by_label)
    selected_agent_label, set_selected_agent_label = solara.use_state(
        agent_options[0] if agent_options else None
    )

    selected_label = selected_agent_label
    if selected_label not in agents_by_label and agent_options:
        selected_label = agent_options[0]

    with solara.Card(title="Tasks", margin=0):
        if not agent_options:
            solara.Markdown("No agents available.")
            return

        solara.Select(
            label="Agent",
            values=agent_options,
            value=selected_label,
            on_value=set_selected_agent_label,
            dense=True,
        )

        agent = agents_by_label[selected_label]
        internal_state = agent.internal_state
        state_levels = [
            ("Hunger", internal_state.hunger),
            ("Toilet need", internal_state.toilet_need),
        ]
        if internal_state.fatigue is not None:
            state_levels.append(("Fatigue", internal_state.fatigue))

        with solara.Card(title="Internal State", margin=0):
            with solara.Column(gap="8px"):
                for label, level in state_levels:
                    with solara.Row(style={"align-items": "center", "gap": "12px"}):
                        solara.Markdown(f"**{label}: {level:.0%}**")
                        solara.ProgressLinear(value=level * 100, color="primary")

        rows: list[dict[str, str]] = [
            {
                "Task": task.task_type.name,
                "Status": task.progress.name,
                "Due Time": str(task.time_due),
                "Start Time": str(task.time_started),
                "End Time": str(task.time_completed),
            }
            for task in agent.tasks
        ]

        with solara.Card(margin=0):
            with solara.Column(gap="8px"):
                solara.Markdown("""
                    **Legend:** \n
                    - 🔵 Not Started

                    - 🚶 Moving to Location

                    - ⏸️ Suspended

                    - ⏳ In Progress

                    - ✅ Completed
                    """)

            with solara.Column(
                gap="8px", margin=0, style={"overflow": "auto", "max-height": "400px"}
            ):
                if not rows:
                    solara.Markdown("This agent has no tasks.")
                for row in rows:
                    status = STATUS_DICT[row["Status"]]

                    task_name = row["Task"].replace("_", " ").title()

                    with solara.Row(
                        style={
                            "align-items": "center",
                            "padding": "8px 12px",
                            "border-radius": "8px",
                            "background-color": "#2a2a2a",
                            "margin-bottom": "4px",
                        }
                    ):
                        solara.Markdown(f"### {status}")

                        solara.Markdown(f"**{task_name}**")

                        solara.Markdown(f"Due: `{row['Due Time']}`")

                        solara.Markdown(f"Start: `{row['Start Time']}`")

                        solara.Markdown(f"End: `{row['End Time']}`")


@solara.lab.task
def run_contact_analysis(distance_threshold: float, bins: int) -> Path:
    """Run a full headless simulation and return the contact analysis directory."""
    output_dir = Path(tempfile.mkdtemp(prefix="amr_hub_contacts_"))
    run_and_analyse_contacts(
        output_dir, distance_threshold=distance_threshold, bins=bins
    )
    return output_dir / "contact_analysis"


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def ContactAnalysisComponent() -> None:
    """Run the simulation once without animation and show the contact analysis."""
    threshold = solara.use_reactive(0.1)
    bins = solara.use_reactive(50)

    with solara.Card(title="Contact analysis", margin=0):
        solara.InputFloat(label="Contact distance threshold", value=threshold)
        solara.InputInt(label="Heatmap bins", value=bins)
        solara.Button(
            "Run simulation & analyse contacts",
            on_click=lambda: run_contact_analysis(threshold.value, bins.value),
            color="primary",
            disabled=run_contact_analysis.pending,
        )
        if run_contact_analysis.pending:
            solara.Markdown("Running the full simulation, this may take a while...")
            solara.ProgressLinear(True)
        elif run_contact_analysis.error:
            solara.Error(f"Contact analysis failed: {run_contact_analysis.exception}")
        elif run_contact_analysis.finished:
            analysis_dir: Path = run_contact_analysis.value
            for image in [
                analysis_dir / "contact_timeseries.png",
                *sorted(analysis_dir.glob("contact_heatmap*.png")),
            ]:
                solara.Image(str(image), width="100%")


model = HospitalABM()


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def SimulationPage() -> None:
    """Animated, step-by-step simulation view."""
    SolaraViz(
        model,
        components=[
            FloorplanComponent,
            AgentTaskTableComponent,
        ],  # pyright: ignore[reportArgumentType]
        name="AMR-HUB Hospital Simulation",
        play_interval=100,
        render_interval=100,
        measures=[
            "Current hospital state",
            lambda m: f"Simulation time: {m.simulation.time}",
            lambda m: f"Agents: {len(m.simulation.agents)}",
        ],
    )


@solara.component  # pyright: ignore[reportPrivateImportUsage]
def ContactAnalysisPage() -> None:
    """Separate tab: single headless run with contact analysis."""
    with solara.Column(style={"padding": "16px"}):
        ContactAnalysisComponent()


routes = [
    solara.Route(path="/", component=SimulationPage, label="Simulation"),
    solara.Route(
        path="contact-analysis",
        component=ContactAnalysisPage,
        label="Contact analysis",
    ),
]
