"""
3D Asset and BVH Environment Query Viewer for AMR-Hub.

UCLARC: Nicolin Govender (5/5/26)
Loads extracted CAD floor plans (.npz) and simulates agent spatial queries.
"""

import logging
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# Setup standard logger
logger = logging.getLogger(__name__)

# Type Aliases for Strong Typing
Point3D = tuple[float, float, float]


# =============================================================================
# 0] Brute Force BVH Query for testing Geometry
# =============================================================================
def distance(p1: Point3D | tuple[float, ...], p2: np.ndarray) -> float:
    """Calculate 2D distance for agent plane movement tracking."""
    return float(np.linalg.norm(np.array(p1[:2]) - np.array(p2[:2])))


def query_environment(
    agent_pos: Point3D, data: np.lib.npyio.NpzFile
) -> tuple[str, int]:
    """Simulate an Agent querying its surroundings using loaded .npz data."""
    logger.info("Agent querying env from %s", agent_pos[:2])

    # 1. Nearest Room
    room_coords: np.ndarray = data["room_coords"]
    room_names: np.ndarray = data["room_names"]
    distances_to_rooms: list[float] = [distance(agent_pos, rc) for rc in room_coords]
    nearest_room_idx: int = int(np.argmin(distances_to_rooms))
    current_room: str = str(room_names[nearest_room_idx])

    # 2. Nearest Bed
    beds: np.ndarray = data["beds"]  # [min_x, min_y, max_x, max_y]
    closest_bed_id: int = -1
    min_bed_dist: float = float("inf")

    for i, b in enumerate(beds):
        bed_center: np.ndarray = np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])
        dist: float = distance(agent_pos, bed_center)
        if dist < min_bed_dist:
            min_bed_dist = dist
            closest_bed_id = i + 1

    logger.info("Location identified: %s", current_room)
    logger.info("Closest Bed: Bed %s (Distance: %.2fm)", closest_bed_id, min_bed_dist)
    return current_room, closest_bed_id


# =============================================================================
# 1] Loads created floor plan and validates extraction
# =============================================================================
def visualize(
    npz_path: str = "../python-code/tests/inputs/GPU_floorplan_simple_a.npz",
    agent_pos: Point3D = (2.0, 13.0, 1.0),
) -> None:
    """Load compiled data and display the 3D asset scene layout."""
    logger.info("Loading Data from %s", npz_path)

    file_path = Path(npz_path)
    if not file_path.exists():
        logger.error("NPZ file not found: %s", npz_path)
        return

    data: np.lib.npyio.NpzFile = np.load(str(file_path), allow_pickle=True)

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")

    # B. Plot Extruded 3D Walls
    verts: np.ndarray = data["wall_vertices"]
    indices: np.ndarray = data["wall_indices"]

    if len(verts) > 0 and len(indices) > 0:
        triangles: np.ndarray = verts[indices.reshape(-1, 3)]
        mesh_col = Poly3DCollection(
            triangles, alpha=0.2, edgecolors="k", facecolors="gray"
        )
        ax.add_collection3d(mesh_col)

    # C. Plot Doors as 2D lines on the floor for visibility
    for d in data["doors"]:
        ax.plot(
            [d[0][0], d[1][0]],
            [d[0][1], d[1][1]],
            zs=[0.0, 0.0],
            color="green",
            linewidth=3,
            linestyle="--",
            label="Door",
        )

    # D. Plot Beds as 2D rectangles on the floor
    for i, b in enumerate(data["beds"]):
        xs: list[float] = [b[0], b[2], b[2], b[0], b[0]]
        ys: list[float] = [b[1], b[1], b[3], b[3], b[1]]
        zs: list[float] = [0.0, 0.0, 0.0, 0.0, 0.0]
        ax.plot(xs, ys, zs, color="blue", linewidth=2, label="Bed" if i == 0 else "")
        ax.text(
            (b[0] + b[2]) / 2,
            (b[1] + b[3]) / 2,
            0.1,
            f"Bed {i + 1}",
            ha="center",
            va="center",
            fontsize=8,
            color="blue",
        )

    # E. Plot Room Labels
    for coords, name in zip(data["room_coords"], data["room_names"], strict=False):
        ax.text(
            coords[0],
            coords[1],
            3.0,
            str(name),
            fontsize=12,
            fontweight="bold",
            color="purple",
            ha="center",
        )

    # F. Agent Query
    current_room, closest_bed = query_environment(agent_pos, data)
    ax.scatter(*agent_pos, color="red", s=100, zorder=5, label="Agent")

    # G. Set Axes Limits based on wall vertices
    if len(verts) > 0:
        ax.set_xlim([np.min(verts[:, 0]) - 1, np.max(verts[:, 0]) + 1])
        ax.set_ylim([np.min(verts[:, 1]) - 1, np.max(verts[:, 1]) + 1])
        ax.set_zlim([0.0, np.max(verts[:, 2]) + 1])

    ax.set_xlabel("X (meters)")
    ax.set_ylabel("Y (meters)")
    ax.set_zlabel("Z (meters)")
    ax.set_title(
        f"3D Asset Viewer\nAgent in: {current_room} | Nearest: Bed {closest_bed}"
    )

    handles, labels = ax.get_legend_handles_labels()
    by_label: dict[str, Any] = dict(zip(labels, handles, strict=False))
    ax.legend(by_label.values(), by_label.keys())

    plt.show()


# =============================================================================
if __name__ == "__main__":
    # Configure logging context for standalone execution execution path
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    visualize()
