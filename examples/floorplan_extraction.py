"""
Example usage of polygon extraction process.

Note that data paths and config paths are dummies.
"""

import logging
from pathlib import Path

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


def main() -> None:
    """Run main routine."""
    data_path = Path("floorplan.dxf")
    config_path = Path("./config.yaml")
    output_path = Path("./output.yaml")

    pec = config_from_yaml(config_path)

    gdf = extract_polygons(data_path, pec)

    logger.info("Extracted %s polygons", len(gdf))

    rooms = polygons_to_rooms(
        gdf,
        room_name_column=pec.polygons.polygon_label_target,
        door_column=pec.doors.out_col if pec.doors else None,
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
