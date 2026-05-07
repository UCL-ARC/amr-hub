# ruff: noqa: D100, D103, E501, ANN201, T201, ANN001
# mypy: ignore-errors
import ezdxf


#==================================================================================================
def generate_complex_hospital(filename="../../../gpu_data/FloorPlan.dxf"):
    print("Generating FloorPlan")
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # 0. Create Layers
    doc.layers.add("WALLS", color=7)
    doc.layers.add("DOORS", color=3)
    doc.layers.add("BEDS", color=1)
    doc.layers.add("ROOM_LABELS", color=5)

    # 1. Walls (Segmented to prevent "Wall Stealing")
    walls = [
        # Corridor
        # (Only the bottom wall remains solid. The open sides will be closed by doors below)
        ((0, 0), (10, 0)), ((10, 0), (20, 0)),       # Bottom Wall (Segmented for better midpoints)

        # ICU Ward
        ((0, 5), (0, 15)),                           # Left Wall
        ((0, 15), (10, 15)),                         # Top Wall
        ((10, 15), (10, 5)),                         # Right Wall (Shared with STD)
        ((0, 5), (2, 5)), ((3, 5), (10, 5)),         # Bottom Walls (Segmented, leaving 1m gap for Door)

        # Standard Ward
        ((10, 15), (20, 15)),                        # Top Wall
        ((20, 15), (20, 5)),                         # Right Wall
        ((10, 5), (12, 5)), ((13, 5), (20, 5))       # Bottom Walls (Segmented, leaving 1m gap for Door)
    ]
    for start, end in walls:
        msp.add_line(start, end, dxfattribs={"layer": "WALLS"})

    # 2. Doors (Closing gaps in wards and closing the open sides of the corridor)
    doors = [
        # Internal Ward Doors
        ((2, 5), (3, 5)),    # ICU Door
        ((12, 5), (13, 5)),  # Standard Ward Door

        # Exterior Corridor Doors (Closing the open sides)
        ((0, 0), (0, 5)),    # West Exit Double Doors
        ((20, 0), (20, 5))   # East Exit Double Doors
    ]
    for start, end in doors:
        msp.add_line(start, end, dxfattribs={"layer": "DOORS"})

    # 3. Beds (Rectangles represented as 4 lines)
    beds = [
        # ICU Bed 1
        [((1, 12), (3, 12)), ((3, 12), (3, 14)), ((3, 14), (1, 14)), ((1, 14), (1, 12))],
        # Standard Bed 1
        [((11, 12), (13, 12)), ((13, 12), (13, 14)), ((13, 14), (11, 14)), ((11, 14), (11, 12))]
    ]
    for bed_lines in beds:
        for start, end in bed_lines:
            msp.add_line(start, end, dxfattribs={"layer": "BEDS"})

    # 4. Room Labels (Placed perfectly in the center of their respective bounding boxes)
    msp.add_text("CORRIDOR", dxfattribs={"layer": "ROOM_LABELS", "height": 0.5}).set_placement((10, 2.5))
    msp.add_text("ICU_WARD", dxfattribs={"layer": "ROOM_LABELS", "height": 0.5}).set_placement((5, 10))
    msp.add_text("STD_WARD", dxfattribs={"layer": "ROOM_LABELS", "height": 0.5}).set_placement((15, 10))

    doc.saveas(filename)
    print(f" Saved to {filename}")
#==================================================================================================

#==================================================================================================
if __name__ == "__main__":
    generate_complex_hospital()
#==================================================================================================
