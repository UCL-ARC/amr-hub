"""Solara app for browser-based AMR Hub ABM visualization."""
# ruff: noqa: N802

from amr_hub_abm.agent.enums import AgentType
import solara
from matplotlib.figure import Figure
from mesa.visualization import SolaraViz
from mesa.visualization.utils import update_counter
import qrcode

from amr_hub_abm.mesa_wrapper import HospitalABM

STATUS_DICT = {
    "NOT_STARTED": "🔵",
    "MOVING_TO_LOCATION": "🚶",
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
    """Render a table of tasks for one agent."""
    update_counter.get()

    agent = [
        agent
        for agent in model.simulation.agents
        if agent.agent_type == AgentType.HEALTHCARE_WORKER
    ][0]
    tasks = agent.tasks

    rows: list[dict[str, str]] = [
        {
            "Task": str(task.task_type.name),
            "Status": str(task.progress.name),
            "Due Time": str(task.time_due),
            "Start Time": str(task.time_started),
            "End Time": str(task.time_completed),
        }
        for task in tasks
    ]

    with solara.Card(title="Tasks", margin=0):
        with solara.Card(margin=0):
            with solara.Column(gap="8px"):
                solara.Markdown("""
                    **Legend:** \n
                    - 🔵 Not Started

                    - 🚶 Moving to Location

                    - ⏳ In Progress

                    - ✅ Completed
                    """)

            with solara.Column(
                gap="8px", margin=0, style={"overflow": "auto", "max-height": "400px"}
            ):
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


page = SolaraViz(
    HospitalABM(),
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
