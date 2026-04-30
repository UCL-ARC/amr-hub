"""Solara app for browser-based AMR Hub ABM visualization."""
# ruff: noqa: N802

import solara
from matplotlib.figure import Figure
from mesa.visualization import SolaraViz
from mesa.visualization.utils import update_counter

from amr_hub_abm.mesa_wrapper import HospitalABM


@solara.component
def FloorplanComponent(model: HospitalABM) -> None:
    """Render the hospital floorplan with current agent positions."""
    update_counter.get()  # subscribe to step events
    fig = Figure(figsize=(10, 6))
    n_floors = len(model.simulation.space[0].floors)
    axes = fig.subplots(nrows=n_floors, ncols=1)
    if not isinstance(axes, (list, tuple)):
        axes = [axes]
    model.simulation.space[0].plot_building(
        axes=list(axes),
        agents=model.simulation.agents,
        trajectory=False,
    )
    fig.suptitle(
        f"Time: {model.simulation.time}/{model.simulation.total_simulation_time}"
    )
    solara.FigureMatplotlib(fig)


page = SolaraViz(
    HospitalABM(),
    components=[FloorplanComponent],
    name="AMR-HUB Hospital Simulation",
    play_interval=50,
    render_interval=1000,
)
