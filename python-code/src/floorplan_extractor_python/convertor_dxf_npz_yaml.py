"""
DXF to NPZ/YAML Compiler for AMR-Hub.

UCLARC: Nicolin Govender (5/5/26)
Reads DXG/CAD Line formats and creates an .npz array (for GPU Physics).
Writes a .yaml configuration file for Python logic.
"""

import logging
from pathlib import Path
from typing import Any

import ezdxf
import numpy as np
import yaml

# Setup standard logger
logger = logging.getLogger(__name__)

# Type Aliases for Strong Typing (Modern Python 3.9+ syntax)
Point2D = tuple[float, float]
LineSegment = tuple[Point2D, Point2D]
RoomLabel = tuple[float, float, str]
AssetData = dict[str, list[Any]]


# =============================================================================
# 1. Creates a 3D Mesh for direct BVH Queries npz
# =============================================================================
def extrude_to_mesh(
    segments: list[LineSegment], height: float = 2.25
) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert 2D line segments into 3D vertical quads composed of triangles.

    Returns flattened Structure of Arrays (SoA) for vertices and indices.
    """
    logger.info("Extruding walls to height 3D: %sm", height)
    vertices: list[list[float]] = []
    indices: list[int] = []
    idx_offset: int = 0

    for p1, p2 in segments:
        if np.allclose(p1, p2):
            continue

        vertices.extend(
            [
                [p1[0], p1[1], 0.0],
                [p2[0], p2[1], 0.0],
                [p2[0], p2[1], height],
                [p1[0], p1[1], height],
            ]
        )

        indices.extend(
            [
                idx_offset,
                idx_offset + 1,
                idx_offset + 2,
                idx_offset,
                idx_offset + 2,
                idx_offset + 3,
            ]
        )

        idx_offset += 4

    v_array: np.ndarray = np.array(vertices, dtype=np.float32)
    i_array: np.ndarray = np.array(indices, dtype=np.int32)

    return v_array, i_array


# =============================================================================
# 2. YAML Generation
# =============================================================================
def generate_semantic_yaml(
    asset_data: AssetData, bed_aabbs: list[list[float]], yaml_path: str
) -> None:
    """
    Group raw lines into semantic rooms based on proximity to labels.

    Exports a YAML file compatible with AMR-HUB SpaceInputReader.
    """
    room_labels: list[RoomLabel] = asset_data.get("rooms", [])

    if not room_labels:
        logger.warning("No room labels found. Cannot generate YAML.")
        return

    # Initialize empty room schemas
    room_dicts: dict[str, dict[str, Any]] = {
        name: {"name": name, "walls": [], "doors": [], "contents": []}
        for x, y, name in room_labels
    }

    def dist(p1: Point2D, p2: Point2D) -> float:
        """Calculate Euclidean distance between two points."""
        return float(np.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2))

    # 1. Assign Walls to the closest room
    for w in asset_data["walls"]:
        mid_x: float = (w[0][0] + w[1][0]) / 2.0
        mid_y: float = (w[0][1] + w[1][1]) / 2.0
        closest_room: RoomLabel = min(
            room_labels, key=lambda r: dist((mid_x, mid_y), (r[0], r[1]))
        )
        room_dicts[closest_room[2]]["walls"].append(
            [float(w[0][0]), float(w[0][1]), float(w[1][0]), float(w[1][1])]
        )

    # 2. Assign Doors to TWO closest rooms (SpaceInputReader validation)
    for d in asset_data["doors"]:
        mid_x = (d[0][0] + d[1][0]) / 2.0
        mid_y = (d[0][1] + d[1][1]) / 2.0
        sorted_rooms: list[RoomLabel] = sorted(
            room_labels, key=lambda r: dist((mid_x, mid_y), (r[0], r[1]))
        )

        if len(sorted_rooms) >= 2:
            for idx in [0, 1]:
                room_dicts[sorted_rooms[idx][2]]["doors"].append(
                    [float(d[0][0]), float(d[0][1]), float(d[1][0]), float(d[1][1])]
                )

    # 3. Assign Beds as contents
    for b in bed_aabbs:
        mid_x = (b[0] + b[2]) / 2.0
        mid_y = (b[1] + b[3]) / 2.0
        closest_room = min(
            room_labels, key=lambda r: dist((mid_x, mid_y), (r[0], r[1]))
        )
        room_dicts[closest_room[2]]["contents"].append(
            {"type": "BED", "position": [float(mid_x), float(mid_y)]}
        )

    # 4. Validation Pass: Filter out mathematically invalid rooms
    valid_rooms: list[dict[str, Any]] = []
    for room_name, room_data in room_dicts.items():
        num_walls: int = len(room_data["walls"])
        num_doors: int = len(room_data["doors"])
        total_bnds: int = num_walls + num_doors

        if total_bnds >= 3:
            valid_rooms.append(room_data)
        else:
            logger.warning(
                "Dropping Room '%s': Acquired %s boundaries (%s walls, "
                "%s doors). Needs at least 3 to close.",
                room_name,
                total_bnds,
                num_walls,
                num_doors,
            )

    # 5. Format according to AMR-HUB specification
    yaml_data: dict[str, Any] = {
        "building": {
            "name": "Hospital_Main",
            "address": "Auto-Generated",
            "floors": [{"level": 0, "rooms": valid_rooms}],
        }
    }

    with Path(yaml_path).open("w") as f:
        yaml.dump(yaml_data, f, sort_keys=False, default_flow_style=False)
    logger.info("Generated Semantic YAML: %s", yaml_path)


# =============================================================================
# 3. Main reading function
# =============================================================================
def compile_semantic_dxf(dxf_path: str, npz_path: str, yaml_path: str) -> None:
    """Read a DXF file and compile it into GPU NPZ and structural YAML."""
    logger.info("Compiling DXF: %s", dxf_path)

    try:
        doc = ezdxf.readfile(dxf_path)
    except OSError:
        logger.exception("Not a valid DXF file -> %s", dxf_path)
        return

    msp = doc.modelspace()
    asset_data: AssetData = {"walls": [], "doors": [], "beds": [], "rooms": []}

    # 1. Extract Entities
    for entity in msp:
        layer: str = entity.dxf.layer
        if entity.dxftype() == "LINE":
            start: Point2D = (entity.dxf.start.x, entity.dxf.start.y)
            end: Point2D = (entity.dxf.end.x, entity.dxf.end.y)
            if layer == "WALLS":
                asset_data["walls"].append((start, end))
            elif layer == "DOORS":
                asset_data["doors"].append((start, end))
            elif layer == "BEDS":
                asset_data["beds"].append((start, end))
        elif entity.dxftype() == "TEXT" and layer == "ROOM_LABELS":
            pos: Point2D = (entity.dxf.insert.x, entity.dxf.insert.y)
            asset_data["rooms"].append((pos[0], pos[1], entity.dxf.text))

    # 2. Convert Beds to AABBs
    bed_aabbs: list[list[float]] = []
    if asset_data["beds"]:
        pts: np.ndarray = np.array(asset_data["beds"]).reshape(-1, 2)
        for i in range(0, len(pts), 8):
            if i + 8 <= len(pts):
                bed_pts: np.ndarray = pts[i : i + 8]
                min_pt: np.ndarray = np.min(bed_pts, axis=0)
                max_pt: np.ndarray = np.max(bed_pts, axis=0)
                bed_aabbs.append(
                    [
                        float(min_pt[0]),
                        float(min_pt[1]),
                        float(max_pt[0]),
                        float(max_pt[1]),
                    ]
                )

    room_coords: list[list[float]] = [
        [float(r[0]), float(r[1])] for r in asset_data["rooms"]
    ]
    room_names: list[str] = [str(r[2]) for r in asset_data["rooms"]]

    # 3. Export NPZ for GPU
    v_array, i_array = extrude_to_mesh(asset_data["walls"], height=2.25)
    np.savez_compressed(
        npz_path,
        wall_vertices=v_array,
        wall_indices=i_array,
        doors=np.array(asset_data["doors"], dtype=np.float32),
        beds=np.array(bed_aabbs, dtype=np.float32),
        room_coords=np.array(room_coords, dtype=np.float32),
        room_names=np.array(room_names),
    )
    logger.info("Compiled BVH Asset to %s", npz_path)

    # 4. Generate YAML
    generate_semantic_yaml(asset_data, bed_aabbs, yaml_path)


# =============================================================================
if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    compile_semantic_dxf(
        dxf_path="../python-code/tests/inputs/GPU_FloorPlan.dxf",
        npz_path="../python-code/tests/inputs/GPU_floorplan_simple_a.npz",
        yaml_path="../python-code/tests/inputs/GPU_floorplan_simple_a.yml",
    )
