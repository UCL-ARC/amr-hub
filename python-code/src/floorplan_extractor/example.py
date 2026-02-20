"""
Example usage of polygon extraction process.

Note that data paths and config paths are dummies.
"""

import logging
from pathlib import Path

from dxf_polygon_extraction import config_from_yaml, extract_polygons

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run main routine."""
    data_path = Path("floorplan.dxf")
    config_path = Path("./config.yaml")
    pec = config_from_yaml(config_path)

    gdf = extract_polygons(data_path, pec)

    logger.info("Extracted %s polygons", len(gdf))

    if __name__ == "__main__":
        main()
