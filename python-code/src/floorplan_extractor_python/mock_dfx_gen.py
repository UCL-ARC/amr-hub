"""
Mock DXF Floor Plan Generator for AMR-Hub.

UCLARC: Nicolin Govender (5/5/26)
Generates a synthetic hospital layout DXF file for testing.
"""

import logging
from pathlib import Path

import ezdxf

# Setup standard logger
logger = logging.getLogger(__name__)

# Type Aliases for Strong Typing
Point2D = tuple[float, float]
LineSegment = tuple[Point2D, Point2D]


# =============================================================================
def generate_complex_hospital(
    filename: str = "../../../gpu_data/FloorPlan.dxf",
) -> None:
    """
    Generate a complex mock hospital layout with semantic layers.

    Creates walls, doors, beds, and room labels for validation testing.
    """
    logger.info("Generating FloorPlan")
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # 0. Create Layers
    doc.layers.add("WALLS", color=7)
    doc.layers.add("DOORS", color=3)
    doc.layers.add("BEDS", color=1)
    doc.layers.add("ROOM_LABELS", color=5)

    # 1. Walls (Segmented to prevent "Wall Stealing")
    walls: list[LineSegment] = [
        # Corridor bottom wall
        ((0, 0), (10, 0)),
        ((10, 0), (20, 0)),
        # ICU Ward
        ((0, 5), (0, 15)),
        ((0, 15), (10, 15)),
        ((10, 15), (10, 5)),
        ((0, 5), (2, 5)),
        ((3, 5), (10, 5)),
        # Standard Ward
        ((10, 15), (20, 15)),
        ((20, 15), (20, 5)),
        ((10, 5), (12, 5)),
        ((13, 5), (20, 5)),
    ]
    for start, end in walls:
        msp.add_line(start, end, dxfattribs={"layer": "WALLS"})

    # 2. Doors (Closing gaps in wards and closing corridor open sides)
    doors: list[LineSegment] = [
        # Internal Ward Doors
        ((2, 5), (3, 5)),
        ((12, 5), (13, 5)),
        # Exterior Corridor Doors
        ((0, 0), (0, 5)),
        ((20, 0), (20, 5)),
    ]
    for start, end in doors:
        msp.add_line(start, end, dxfattribs={"layer": "DOORS"})

    # 3. Beds (Rectangles represented as 4 lines)
    beds: list[list[LineSegment]] = [
        # ICU Bed 1
        [
            ((1, 12), (3, 12)),
            ((3, 12), (3, 14)),
            ((3, 14), (1, 14)),
            ((1, 14), (1, 12)),
        ],
        # Standard Bed 1
        [
            ((11, 12), (13, 12)),
            ((13, 12), (13, 14)),
            ((13, 14), (11, 14)),
            ((11, 14), (11, 12)),
        ],
    ]
    for bed_lines in beds:
        for start, end in bed_lines:
            msp.add_line(start, end, dxfattribs={"layer": "BEDS"})

    # 4. Room Labels (Placed perfectly in the center of their bounding boxes)
    txt_attribs: dict[str, str | float] = {
        "layer": "ROOM_LABELS",
        "height": 0.5,
    }
    msp.add_text("CORRIDOR", dxfattribs=txt_attribs).set_placement((10, 2.5))
    msp.add_text("ICU_WARD", dxfattribs=txt_attribs).set_placement((5, 10))
    msp.add_text("STD_WARD", dxfattribs=txt_attribs).set_placement((15, 10))

    # Handle paths safely using pathlib and save the document
    out_path: Path = Path(filename)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))
    logger.info("Saved to %s", out_path)


# =============================================================================
if __name__ == "__main__":
    # Configure logging context for standalone script runtime
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    generate_complex_hospital()
