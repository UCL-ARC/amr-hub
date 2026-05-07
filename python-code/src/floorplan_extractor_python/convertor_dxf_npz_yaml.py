# ruff: noqa: D100, D103, D205, D400, D401, D415, E501, ANN201, T201, ANN001, ANN202, PTH123
import ezdxf
import numpy as np
import yaml

"""
UCLARC: Nicolin Govender
5/5/26
Reads DXG/CAD Line formats and creates an .npz array (for GPU Physics)
5/5/26 writes .yaml configuration file for Python logic
"""

#==================================================================================================
# 1. Creates a 3D Mesh for direct BVH Queries npz
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
        if np.allclose(p1, p2):
            continue

        vertices.extend([
            [p1[0], p1[1], 0.0],
            [p2[0], p2[1], 0.0],
            [p2[0], p2[1], height],
            [p1[0], p1[1], height]
        ])

        indices.extend([
            idx_offset, idx_offset + 1, idx_offset + 2,
            idx_offset, idx_offset + 2, idx_offset + 3
        ])

        idx_offset += 4

    v_array = np.array(vertices, dtype=np.float32)
    i_array = np.array(indices, dtype=np.int32)

    return v_array, i_array
#==================================================================================================


#==================================================================================================
# 2. YAML Generation
#==================================================================================================
def generate_semantic_yaml(asset_data: dict, bed_aabbs: list, yaml_path: str):
    """
    Groups raw lines into semantic rooms based on proximity to room labels
    and exports a YAML file compatible with AMR-HUB SpaceInputReader
    """
    room_labels = asset_data["rooms"]

    if not room_labels:
        print("No room labels found. Cannot generate YAML")
        return

    # Initialize empty room schemas
    room_dicts = {name: {"name": name, "walls": [], "doors": [], "contents": []} for x, y, name in room_labels}

    def dist(p1, p2):
        return np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

    # 1. Assign Walls to the closest room
    for w in asset_data["walls"]:
        mid_x, mid_y = (w[0][0] + w[1][0]) / 2.0, (w[0][1] + w[1][1]) / 2.0
        closest_room = min(room_labels, key=lambda r: dist((mid_x, mid_y), (r[0], r[1])))
        room_dicts[closest_room[2]]["walls"].append([float(w[0][0]), float(w[0][1]), float(w[1][0]), float(w[1][1])])

    # 2. Assign Doors to the TWO closest rooms (Required by SpaceInputReader validation)
    for d in asset_data["doors"]:
        mid_x, mid_y = (d[0][0] + d[1][0]) / 2.0, (d[0][1] + d[1][1]) / 2.0
        sorted_rooms = sorted(room_labels, key=lambda r: dist((mid_x, mid_y), (r[0], r[1])))

        if len(sorted_rooms) >= 2:
            room_dicts[sorted_rooms[0][2]]["doors"].append([float(d[0][0]), float(d[0][1]), float(d[1][0]), float(d[1][1])])
            room_dicts[sorted_rooms[1][2]]["doors"].append([float(d[0][0]), float(d[0][1]), float(d[1][0]), float(d[1][1])])

    # 3. Assign Beds as contents
    for b in bed_aabbs:
        mid_x, mid_y = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        closest_room = min(room_labels, key=lambda r: dist((mid_x, mid_y), (r[0], r[1])))
        room_dicts[closest_room[2]]["contents"].append({
            "type": "BED",
            "position": [float(mid_x), float(mid_y)]
        })

    # 4. Validation Pass: Filter out mathematically invalid rooms
    valid_rooms = []
    for room_name, room_data in room_dicts.items():
        # A closed region is defined by its total boundaries (Walls + Doors)
        num_walls = len(room_data["walls"])
        num_doors = len(room_data["doors"])
        total_boundaries = num_walls + num_doors

        if total_boundaries >= 3:
            valid_rooms.append(room_data)
        else:
            print(f"Dropping Room '{room_name}': Only acquired {total_boundaries} boundaries ({num_walls} walls, {num_doors} doors). Needs at least 3 to close.")

    # 5. Format according to AMR-HUB specification
    yaml_data = {
        "building": {
            "name": "Hospital_Main",
            "address": "Auto-Generated",
            "floors": [{
                "level": 0,
                "rooms": valid_rooms
            }]
        }
    }

    with open(yaml_path, "w") as f:
        yaml.dump(yaml_data, f, sort_keys=False, default_flow_style=False)
    print(f"Generated Semantic YAML: {yaml_path}")
#==================================================================================================


#==================================================================================================
# 3. Main reading function
#==================================================================================================
def compile_semantic_dxf(dxf_path: str, npz_path: str, yaml_path: str):
    print(f"Compiling DXF: {dxf_path}")

    try:
        doc = ezdxf.readfile(dxf_path)
    except OSError:
        print(f"❌ Error: Not a valid DXF file -> {dxf_path}")
        return

    msp = doc.modelspace()
    asset_data = {"walls": [], "doors": [], "beds": [], "rooms": []}

    # 1. Extract Entities
    for entity in msp:
        layer = entity.dxf.layer
        if entity.dxftype() == "LINE":
            start, end = (entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)
            if layer == "WALLS":
                asset_data["walls"].append((start, end))
            elif layer == "DOORS":
                asset_data["doors"].append((start, end))
            elif layer == "BEDS":
                asset_data["beds"].append((start, end))
        elif entity.dxftype() == "TEXT" and layer == "ROOM_LABELS":
            pos = (entity.dxf.insert.x, entity.dxf.insert.y)
            asset_data["rooms"].append((pos[0], pos[1], entity.dxf.text))

    # 2. Convert Beds to AABBs
    bed_aabbs = []
    if asset_data["beds"]:
        pts = np.array(asset_data["beds"]).reshape(-1, 2)
        for i in range(0, len(pts), 8):
            if i + 8 <= len(pts):
                bed_pts = pts[i:i+8]
                min_pt, max_pt = np.min(bed_pts, axis=0), np.max(bed_pts, axis=0)
                bed_aabbs.append([min_pt[0], min_pt[1], max_pt[0], max_pt[1]])

    room_coords = [[r[0], r[1]] for r in asset_data["rooms"]]
    room_names = [r[2] for r in asset_data["rooms"]]

    # 3. Export NPZ for GPU
    v_array, i_array = extrude_to_mesh(asset_data["walls"], height=2.25)
    np.savez_compressed(
        npz_path,
        wall_vertices=v_array,
        wall_indices=i_array,
        doors=np.array(asset_data["doors"], dtype=np.float32),
        beds=np.array(bed_aabbs, dtype=np.float32),
        room_coords=np.array(room_coords, dtype=np.float32),
        room_names=np.array(room_names)
    )
    print(f"Compiled BVH Asset to {npz_path}")

    # 4. Generate YAML
    generate_semantic_yaml(asset_data, bed_aabbs, yaml_path)

#==================================================================================================

#==================================================================================================
if __name__ == "__main__":
    compile_semantic_dxf(
        dxf_path="../../../gpu_data/FloorPlan.dxf",
        npz_path="../../../gpu_data/floorplan_simple_a.npz",
        yaml_path="../../../gpu_data/floorplan_simple_a.yml"
    )
#==================================================================================================
