"""
Example usage of polygon extraction process.

Note that data paths and config paths are dummies.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import yaml
from floorplan_extractor.dxf_polygon_extraction import (
    config_from_yaml,
    extract_polygons,
)
from floorplan_extractor.yaml_construction import (
    build_yaml_structure,
    polygons_to_rooms,
    register_yaml_representers,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
register_yaml_representers()


def plot_extracted_floorplan(
    production_gdf,
    *,
    room_name_column: str,
    door_column: str | None,
    output_path: Path,
) -> None:
    """Plot extracted room polygons and door segments to a static image."""
    fig, ax = plt.subplots(figsize=(12, 10))

    production_gdf.boundary.plot(ax=ax, color="black", linewidth=0.6)

    if door_column is not None and door_column in production_gdf.columns:
        for door_segments in production_gdf[door_column]:
            for x1, y1, x2, y2 in door_segments:
                ax.plot([x1, x2], [y1, y2], color="brown", linewidth=1.2)

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

    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def main() -> None:
    """Run main routine."""
    data_path = Path("floorplan.dxf")
    config_path = Path("./config.yaml")
    output_path = Path("./output.yaml")
    plot_path = output_path.with_suffix(".png")

    pec = config_from_yaml(config_path)

    gdf = extract_polygons(data_path, pec)

    logger.info("Extracted %s polygons", len(gdf))

    production_gdf = gdf.loc[gdf["has_label"], :]
    review_gdf = gdf.loc[gdf["needs_review"], :]

    if len(review_gdf) > 0:
        logger.warning("Identified %s rooms for review", len(review_gdf))
        logger.warning(review_gdf.head())

    rooms = polygons_to_rooms(
        production_gdf,
        room_name_column=pec.polygons.polygon_label_target,
        door_column=pec.doors.out_col if pec.doors else None,
    )

    logger.info("Writing floorplan plot to %s", plot_path)
    plot_extracted_floorplan(
        production_gdf,
        room_name_column=pec.polygons.polygon_label_target,
        door_column=pec.doors.out_col if pec.doors else None,
        output_path=plot_path,
    )

    logger.info("Converting rooms to yaml")
    data = build_yaml_structure(
        building_name="Sample Hospital",
        building_address="123 Health St, Wellness City",
        floor_level=0,
        rooms=rooms,
    )

    logger.info("Writing building yaml to %s", output_path)
    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            sort_keys=False,
        )


if __name__ == "__main__":
    main()
