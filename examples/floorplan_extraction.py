"""Run DXF floorplan extraction and write YAML plus diagnostics."""

import argparse
import logging
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
import yaml
from floorplan_extractor.dxf_polygon_extraction import (
    config_from_yaml,
    extract_polygons,
)
from floorplan_extractor.shared_walls import (
    SharedWallDetectionResult,
    candidate_midline,
    rejection_overlap_lines,
)
from floorplan_extractor.yaml_construction import (
    build_yaml_structure,
    polygons_to_rooms,
    register_yaml_representers,
)

DEFAULT_DXF_PATH = Path("floorplan.dxf")
DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_OUTPUT_PATH = Path("output.yaml")
DEFAULT_DIAGNOSTIC_PATH = Path("output_diagnostic.png")
DEFAULT_BUILDING_NAME = "Sample Hospital"
DEFAULT_BUILDING_ADDRESS = "123 Health St, Wellness City"
DEFAULT_FLOOR_LEVEL = 0
MAX_REJECTION_MARKERS = 50

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
register_yaml_representers()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the local extraction example."""
    parser = argparse.ArgumentParser(
        description="Extract room polygons from a DXF floorplan.",
    )
    parser.add_argument("--dxf", type=Path, default=DEFAULT_DXF_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--diagnostic",
        type=Path,
        default=DEFAULT_DIAGNOSTIC_PATH,
    )

    return parser.parse_args()


def plot_extracted_floorplan(
    production_gdf,
    *,
    room_name_column: str,
    door_column: str | None,
    output_path: Path,
) -> None:
    """Plot rooms, doors, and shared-wall decisions to a static image."""
    fig, ax = plt.subplots(figsize=(12, 10))

    production_gdf.plot(
        ax=ax,
        facecolor="#d8ecff",
        edgecolor="#1f2937",
        linewidth=0.5,
        alpha=0.35,
    )

    if door_column is not None and door_column in production_gdf.columns:
        door_label = "Canonical door opening"
        for x1, y1, x2, y2 in _unique_door_segments(production_gdf[door_column]):
            ax.plot(
                [x1, x2],
                [y1, y2],
                color="white",
                linewidth=3.6,
                solid_capstyle="butt",
                label="_nolegend_",
                zorder=4,
            )
            ax.plot(
                [x1, x2],
                [y1, y2],
                color="#dc2626",
                linewidth=2.0,
                solid_capstyle="butt",
                label=door_label,
                zorder=5,
            )
            door_label = "_nolegend_"

    # _plot_shared_wall_diagnostics(
    #     ax,
    #     production_gdf.attrs.get("shared_wall_detection"),
    # )

    for _, row in production_gdf.iterrows():
        label_point = row.geometry.representative_point()
        ax.text(
            label_point.x,
            label_point.y,
            str(row[room_name_column]),
            fontsize=4,
            ha="center",
            va="center",
        )

    min_x, min_y, max_x, max_y = production_gdf.total_bounds
    margin = max(max_x - min_x, max_y - min_y) * 0.02
    ax.set_xlim(min_x - margin, max_x + margin)
    ax.set_ylim(min_y - margin, max_y + margin)
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()
    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles, strict=False))
    if unique:
        ax.legend(unique.values(), unique.keys(), loc="upper right", fontsize=7)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def _unique_door_segments(door_values):
    """Return canonical door segments once, including doors shared by two rooms."""
    segments = {}

    for room_doors in door_values:
        for x1, y1, x2, y2 in room_doors:
            start = (float(x1), float(y1))
            end = (float(x2), float(y2))
            key = tuple(
                sorted(
                    (
                        (round(start[0], 8), round(start[1], 8)),
                        (round(end[0], 8), round(end[1], 8)),
                    )
                )
            )
            segments.setdefault(key, (*start, *end))

    return segments.values()


def _plot_shared_wall_diagnostics(
    ax,
    detection: object,
) -> None:
    if not isinstance(detection, SharedWallDetectionResult):
        return

    accepted_label = "Accepted shared wall"
    for candidate in detection.candidates:
        line = candidate_midline(candidate)
        x, y = line.xy
        ax.plot(
            x,
            y,
            color="#16a34a",
            linewidth=1.6,
            label=accepted_label,
        )
        accepted_label = "_nolegend_"

    rejection_labels = {
        "ambiguous_match": "Ambiguous shared wall",
        "normalisation_invalid_geometry": "Rejected: invalid geometry",
        "rejected": "Rejected shared wall",
    }
    for rejection in detection.rejections[:MAX_REJECTION_MARKERS]:
        if rejection.reason == "ambiguous_match":
            label_key = "ambiguous_match"
            colour = "#dc2626"
            linestyle = "--"
        elif rejection.reason == "normalisation_invalid_geometry":
            label_key = "normalisation_invalid_geometry"
            colour = "#7c3aed"
            linestyle = ":"
        else:
            label_key = "rejected"
            colour = "#f59e0b"
            linestyle = "--"
        label = rejection_labels[label_key]
        for line in rejection_overlap_lines(rejection):
            x, y = line.xy
            ax.plot(
                x,
                y,
                color=colour,
                linewidth=1.1,
                linestyle=linestyle,
                alpha=0.8,
                label=label,
            )
            label = "_nolegend_"
        rejection_labels[label_key] = "_nolegend_"

    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles, strict=False))
    if unique:
        ax.legend(unique.values(), unique.keys(), loc="upper right", fontsize=7)


def main() -> None:
    """Run main routine."""
    args = parse_args()

    pec = config_from_yaml(args.config)

    gdf = extract_polygons(args.dxf, pec)

    logger.info("Extracted %s polygons", len(gdf))

    production_gdf = gdf.loc[gdf["has_label"], :].copy()
    production_gdf.attrs = dict(gdf.attrs)
    review_gdf = gdf.loc[gdf["needs_review"], :]

    if len(review_gdf) > 0:
        logger.warning("Identified %s rooms for review", len(review_gdf))
        logger.warning(review_gdf.head())

    rooms = polygons_to_rooms(
        production_gdf,
        room_name_column=pec.polygons.polygon_label_target,
        door_column=pec.doors.out_col if pec.doors else None,
    )

    logger.info("Writing floorplan diagnostic plot to %s", args.diagnostic)
    plot_extracted_floorplan(
        production_gdf,
        room_name_column=pec.polygons.polygon_label_target,
        door_column=pec.doors.out_col if pec.doors else None,
        output_path=args.diagnostic,
    )

    logger.info("Converting rooms to yaml")
    data = build_yaml_structure(
        building_name=DEFAULT_BUILDING_NAME,
        building_address=DEFAULT_BUILDING_ADDRESS,
        floor_level=DEFAULT_FLOOR_LEVEL,
        rooms=rooms,
    )

    logger.info("Writing building yaml to %s", args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            sort_keys=False,
        )


if __name__ == "__main__":
    main()
