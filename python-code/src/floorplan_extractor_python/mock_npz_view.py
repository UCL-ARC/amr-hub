# ruff: noqa: D100, D103, D400, D401, D415, E501, ANN201, T201, B905, ANN001
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

"""
UCLARC: Nicolin Govender
5/5/26
Quick Viewer to check extracted CAD files can be queried
"""

#==================================================================================================
# 0] Brute Force BVH Query for testing Geometry
#==================================================================================================
def distance(p1, p2):
    # Using 2D distance for bed/room queries since the agent moves on the XY plane
    return np.linalg.norm(np.array(p1[:2]) - np.array(p2[:2]))

def query_environment(agent_pos, data):
    """Simulates an Agent querying its surroundings using the loaded .npz data"""
    print(f"\n Agent querying env from {agent_pos[:2]}")

    # 1. Nearest Room
    room_coords = data["room_coords"]
    room_names = data["room_names"]
    distances_to_rooms = [distance(agent_pos, rc) for rc in room_coords]
    nearest_room_idx = np.argmin(distances_to_rooms)
    current_room = room_names[nearest_room_idx]

    # 2. Nearest Bed
    beds = data["beds"] # [min_x, min_y, max_x, max_y]
    closest_bed_id = -1
    min_bed_dist = float("inf")

    for i, b in enumerate(beds):
        bed_center = [(b[0]+b[2])/2, (b[1]+b[3])/2]
        dist = distance(agent_pos, bed_center)
        if dist < min_bed_dist:
            min_bed_dist = dist
            closest_bed_id = i + 1

    print(f" Location identified: {current_room}")
    print(f" Closest Bed: Bed {closest_bed_id} (Distance: {min_bed_dist:.2f}m)\n")
    return current_room, closest_bed_id
#==================================================================================================


#==================================================================================================
#1] Loads the created floor plan and does a query to check that the create npz extraction is valid
#==================================================================================================
def visualize(npz_path="../../../gpu_data/floorplan_simple_a.npz", agent_pos=(2.0, 13.0, 1.0)):
    # A. Load compiled data
    print(f"Loading Data from {npz_path}")
    data = np.load(npz_path, allow_pickle=True)

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")

    # B. Plot Extruded 3D Walls
    verts = data["wall_vertices"]
    indices = data["wall_indices"]

    if len(verts) > 0 and len(indices) > 0:
        triangles = verts[indices.reshape(-1, 3)]
        mesh_col = Poly3DCollection(triangles, alpha=0.2, edgecolors="k", facecolors="gray")
        ax.add_collection3d(mesh_col)

    # C. Plot Doors as 2D lines on the floor for visibility
    for d in data["doors"]:
        ax.plot([d[0][0], d[1][0]], [d[0][1], d[1][1]], zs=[0, 0], color="green", linewidth=3, linestyle="--", label="Door")

    # D. Plot Beds as 2D rectangles on the floor
    for i, b in enumerate(data["beds"]):
        # Draw the outline of the AABB
        xs = [b[0], b[2], b[2], b[0], b[0]]
        ys = [b[1], b[1], b[3], b[3], b[1]]
        zs = [0, 0, 0, 0, 0]
        ax.plot(xs, ys, zs, color="blue", linewidth=2, label="Bed" if i==0 else "")
        ax.text((b[0]+b[2])/2, (b[1]+b[3])/2, 0.1, f"Bed {i+1}", ha="center", va="center", fontsize=8, color="blue")

    # E. Plot Room Labels
    for coords, name in zip(data["room_coords"], data["room_names"]):
        ax.text(coords[0], coords[1], 3.0, name, fontsize=12, fontweight="bold", color="purple", ha="center")

    # F. Agent Query Passing 3D pos since the BVH uses that but query is 2D
    current_room, closest_bed = query_environment(agent_pos, data)
    ax.scatter(*agent_pos, color="red", s=100, zorder=5, label="Agent")

    # G. Set Axes Limits based on wall vertices
    if len(verts) > 0:
        ax.set_xlim([np.min(verts[:,0])-1, np.max(verts[:,0])+1])
        ax.set_ylim([np.min(verts[:,1])-1, np.max(verts[:,1])+1])
        ax.set_zlim([0, np.max(verts[:,2])+1])

    ax.set_xlabel("X (meters)")
    ax.set_ylabel("Y (meters)")
    ax.set_zlabel("Z (meters)")
    ax.set_title(f" 3D Asset Viewer\nAgent in: {current_room} | Nearest: Bed {closest_bed}")

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys())

    plt.show()
#==================================================================================================

#==================================================================================================
if __name__ == "__main__":
    visualize()
#==================================================================================================
