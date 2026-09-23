"""Plot resolved source events over loaded model geometry."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

from amr_hub_abm.data_ingestion.reference_locations import (
    EventLocationResolutionStatus,
)
from amr_hub_abm.spatial.plotter import plot_room

if TYPE_CHECKING:
    from pathlib import Path

    from amr_hub_abm.data_ingestion.prepared_events import (
        LocationEventPreparationReport,
    )
    from amr_hub_abm.spatial.room import Room


def _event_style(event_type: str) -> tuple[str, str, str]:
    """Return marker, colour, and label for a resolved event type."""
    if event_type == "attend_patient":
        return "o", "#2563eb", "Resolved patient event"
    if event_type == "door_access":
        return "^", "#dc2626", "Resolved door event"
    return "s", "#7c3aed", "Resolved event"


def plot_location_mapping(
    rooms: list[Room],
    report: LocationEventPreparationReport,
    output_path: Path,
) -> None:
    """
    Plot resolved event coordinates over loaded model rooms.

    Parameters
    ----------
    rooms : list[Room]
        Spatial rooms loaded through the standard model YAML reader.
    report : LocationEventPreparationReport
        Prepared events and their complete reconciliation audit.
    output_path : pathlib.Path
        Destination for the generated PNG image.

    """
    fig, (ax, audit_ax) = plt.subplots(
        1,
        2,
        figsize=(17, 10),
        gridspec_kw={"width_ratios": [4.5, 1.5]},
    )
    for room in rooms:
        plot_room(
            room,
            ax,
            door_color="#9ca3af",
            door_width=0.6,
        )

    resolved = report.audit.loc[
        report.audit["resolution_status"] == EventLocationResolutionStatus.RESOLVED
    ]
    labelled_event_types: set[str] = set()
    labelled_rooms: set[str] = set()
    for _, event in resolved.iterrows():
        event_type = str(event["event_type"])
        marker, colour, label = _event_style(event_type)
        legend_label = label if event_type not in labelled_event_types else "_nolegend_"
        ax.scatter(
            float(event["x"]),
            float(event["y"]),
            marker=marker,
            color=colour,
            edgecolor="white",
            linewidth=0.8,
            s=70,
            label=legend_label,
            zorder=6,
        )
        labelled_event_types.add(event_type)
        ax.annotate(
            str(event["source_event_id"]),
            (float(event["x"]), float(event["y"])),
            xytext=(5, 8),
            textcoords="offset points",
            fontsize=7,
            color=colour,
            zorder=7,
        )
        room_code = str(event["model_room_code"])
        if room_code not in labelled_rooms:
            ax.annotate(
                room_code,
                (float(event["x"]), float(event["y"])),
                xytext=(5, -3),
                textcoords="offset points",
                fontsize=6,
                color="#374151",
                zorder=7,
            )
            labelled_rooms.add(room_code)

    status_counts = report.audit["resolution_status"].value_counts()
    resolved_count = int(status_counts.get(EventLocationResolutionStatus.RESOLVED, 0))
    unresolved_count = len(report.audit) - resolved_count
    fig.suptitle(
        f"Event location reconciliation: {resolved_count} resolved, "
        f"{unresolved_count} unresolved",
        fontsize=16,
    )
    ax.set_aspect("equal", adjustable="box")
    ax.margins(x=0.03, y=0.05)
    ax.set_axis_off()
    handles, labels = ax.get_legend_handles_labels()

    unresolved = report.audit.loc[
        report.audit["resolution_status"] != EventLocationResolutionStatus.RESOLVED
    ]
    audit_ax.set_title("Unresolved events", loc="left", fontweight="bold")
    audit_ax.set_axis_off()
    y_position = 0.94
    for _, event in unresolved.iterrows():
        audit_ax.text(
            0.0,
            y_position,
            str(event["source_event_id"]),
            transform=audit_ax.transAxes,
            fontsize=9,
            fontweight="bold",
            va="top",
        )
        audit_ax.text(
            0.0,
            y_position - 0.035,
            str(event["resolution_status"]),
            transform=audit_ax.transAxes,
            fontsize=8,
            color="#6b7280",
            va="top",
        )
        y_position -= 0.13
    if handles:
        audit_ax.legend(handles, labels, loc="lower left")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
