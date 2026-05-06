import ezdxf
import numpy as np
import argparse
from pathlib import Path

"""
UCLARC: Nicolin Govender
5/5/26
Reads DXG/CAD Line formats and creates a npz array
"""


#==================================================================================================
# 1] Creates a 3D Mesh for direct BVH Queries
#==================================================================================================
def extrude_to_mesh(segments: list[tuple], height: float = 2.25) -> tuple[np.ndarray, np.ndarray]:
    """
    Converts 2D line segments into 3D vertical quads (walls) composed of triangles
    Returns flattened Structure of Arrays (SoA) for vertices and indices
    """
    print(f" Extruding walls to height 3D: {height}m")
    vertices = []
    indices = []
    idx_offset = 0

    for (p1, p2) in segments:
        # A. Filter out degenerate/zero-length lines common in dirty CAD files
        if np.allclose(p1, p2):
            continue

        # Create 4 vertices for the wall (Bottom-Left, Bottom-Right, Top-Right, Top-Left)
        vertices.extend([
            [p1[0], p1[1], 0.0],     # V0
            [p2[0], p2[1], 0.0],     # V1
            [p2[0], p2[1], height],  # V2
            [p1[0], p1[1], height]   # V3
        ])

        # B. Create 2 Triangles for the quad (Counter-Clockwise winding)
        indices.extend([
            idx_offset, idx_offset + 1, idx_offset + 2,      # Triangle 1
            idx_offset, idx_offset + 2, idx_offset + 3       # Triangle 2
        ])

        idx_offset += 4

    v_array = np.array(vertices, dtype=np.float32)
    i_array = np.array(indices, dtype=np.int32)

    print(f"Generated Mesh: {len(v_array)} vertices, {len(i_array)//3} triangles")
    return v_array, i_array
#==================================================================================================


#==================================================================================================
# 2] Main reading function
#==================================================================================================
def compile_semantic_dxf(dxf_path: str, out_path: str):
    print(f" Compiling Semantic DXF: {dxf_path}")

    try:
        doc = ezdxf.readfile(dxf_path)
    except IOError:
        print(f"❌ Error: Not a valid DXF file -> {dxf_path}")
        return

    msp = doc.modelspace()
    asset_data = {
        'walls': [],
        'doors': [],
        'beds':  [],
        'rooms': [],
                 }

    # A. Extract Entities
    for entity in msp:
        layer = entity.dxf.layer

        if entity.dxftype() == 'LINE':
            start, end = (entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)
            if layer == 'WALLS':
                asset_data['walls'].append((start, end))
            elif layer == 'DOORS':
                asset_data['doors'].append((start, end))
            elif layer == 'BEDS':
                # Store raw lines, we will compute AABBs below
                asset_data['beds'].append((start, end))

        elif entity.dxftype() == 'TEXT' and layer == 'ROOM_LABELS':
            pos = (entity.dxf.insert.x, entity.dxf.insert.y)
            asset_data['rooms'].append((pos[0], pos[1], entity.dxf.text))

    # B. Convert Beds from lines to Bounding Boxes (AABBs)
    bed_aabbs = []
    if asset_data['beds']:
        pts = np.array(asset_data['beds']).reshape(-1, 2)
        for i in range(0, len(pts), 8):
            if i + 8 <= len(pts):
                bed_pts = pts[i:i+8]
                min_pt, max_pt = np.min(bed_pts, axis=0), np.max(bed_pts, axis=0)
                bed_aabbs.append([min_pt[0], min_pt[1], max_pt[0], max_pt[1]])

    # C. Separate Room Labels and Coordinates
    room_coords = [[r[0], r[1]] for r in asset_data['rooms']]
    room_names = [r[2] for r in asset_data['rooms']]

    # D. Extrude 2D walls to 3D mesh arrays
    v_array, i_array = extrude_to_mesh(asset_data['walls'], height=2.25)

    # E. Save to a binary blob
    np.savez_compressed(
        out_path,
        wall_vertices=v_array,
        wall_indices=i_array,
        doors=np.array(asset_data['doors'], dtype=np.float32),
        beds=np.array(bed_aabbs, dtype=np.float32),
        room_coords=np.array(room_coords, dtype=np.float32),
        room_names=np.array(room_names)
    )
    print(f"Compiled Semantic Asset to {out_path}")
#==================================================================================================

#==================================================================================================
if __name__ == "__main__":
    # TODO: will add command line input
    compile_semantic_dxf("NG_TestFloorPlan.dxf", "FloorPlan_SimpleA.npz")
#==================================================================================================
