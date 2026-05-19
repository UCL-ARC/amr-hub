# mypy: ignore-errors
"""
GPU Physics Engine for AMR-Hub.

UCLARC: Nicolin Govender (6/5/26).
Integrates existing logic (Tasks/Agents) with GPU Physics (CUDA Warp).
Calculates HashGrid transmission, executes BVH spatial queries,
and records telemetry for the HTML dashboard.
"""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import warp as wp

# Setup standard logger
logger = logging.getLogger(__name__)

# =============================================================================
# Call the GPU Driver
wp.init()
# =============================================================================


# =============================================================================
# A] Agent moves in space
# =============================================================================
@wp.kernel
def cuda_warp_kernel_kinematic_agent_movement(
    mesh: wp.uint64,
    positions: wp.array(dtype=wp.vec3),
    targets: wp.array(dtype=wp.vec2),
    speed: float,
    dt: float,
) -> None:
    """Calculate agent movement and perform wall collision checks via BVH."""
    tid = wp.tid()
    pos = positions[tid]
    target = targets[tid]

    dir_x = target[0] - pos[0]
    dir_y = target[1] - pos[1]
    dist_to_target = wp.sqrt(dir_x * dir_x + dir_y * dir_y)

    if dist_to_target < 0.1:
        return

    dir_x = dir_x / dist_to_target
    dir_y = dir_y / dist_to_target

    step_size = wp.min(speed * dt, dist_to_target)
    next_x = pos[0] + (dir_x * step_size)
    next_y = pos[1] + (dir_y * step_size)
    next_pos = wp.vec3(next_x, next_y, pos[2])

    # BVH Collision Check against walls
    ray_dir = wp.normalize(next_pos - pos)
    hit = wp.mesh_query_ray(mesh, pos, ray_dir, step_size)  # pyright: ignore[reportCallIssue]
    if not hit.result:
        positions[tid] = next_pos


# =============================================================================
# B] Agent Proximity and Disease Spread
# =============================================================================
@wp.kernel
def cuda_warp_kernel_agent_proximity(  # noqa: PLR0913
    grid: wp.uint64,
    positions: wp.array(dtype=wp.vec3),
    statuses: wp.array(dtype=wp.int32),
    floor_ids: wp.array(dtype=wp.int32),
    search_radius: float,
    out_infector: wp.array(dtype=wp.int32),
) -> None:
    """Query a HashGrid to find infected neighbors within a given radius."""
    tid = wp.tid()
    if statuses[tid] == 0:  # SUSCEPTIBLE
        pos = positions[tid]
        my_floor = floor_ids[tid]

        query = wp.hash_grid_query(
            grid,
            pos,
            search_radius,  # type: ignore  # noqa: PGH003
        )  # pyright: ignore[reportArgumentType]
        neighbor = wp.int32(0)

        while wp.hash_grid_query_next(query, neighbor):
            # Same floor and INFECTED
            if (
                neighbor != tid
                and statuses[neighbor] == 2
                and floor_ids[neighbor] == my_floor
            ):
                dist = wp.length(pos - positions[neighbor])
                if dist <= search_radius:
                    out_infector[tid] = neighbor
                    break


# =============================================================================
# C] Python-to-GPU Engine Class
# =============================================================================
class GPUPhysicsEngine:
    """Manages the Warp GPU state for the AMR Hub Simulation."""

    def __init__(
        self, cad_path: str = "tests/inputs/GPU_floorplan_simple_a.npz"
    ) -> None:
        """Initialize the GPU engine, loading geometry for BVH queries."""
        logger.info("Initializing GPU Physics Engine")

        # Look for the file locally or up a directory based on CWD
        target_path: Path = Path(cad_path)
        if not target_path.exists():
            target_path = Path("..") / cad_path

        geom = np.load(str(target_path), allow_pickle=True)

        self.mesh: wp.Mesh = wp.Mesh(
            points=wp.array(geom["wall_vertices"], dtype=wp.vec3),
            indices=wp.array(geom["wall_indices"], dtype=wp.int32),
        )
        self.grid: wp.HashGrid = wp.HashGrid(dim_x=128, dim_y=128, dim_z=128)
        self.search_radius: float = 2.0
        self.telemetry: list[dict[str, Any]] = []
        self.transmission_events: list[dict[str, Any]] = []
        self.current_tick: int = 0

    def step_physics(self, agents: list[Any]) -> None:
        """Synchronize CPU agent state with the GPU and execute a tick."""
        num_agents = len(agents)
        if num_agents == 0:
            return

        # 1. Extract Python state to NumPy
        pos_np = np.zeros((num_agents, 3), dtype=np.float32)
        target_np = np.zeros((num_agents, 2), dtype=np.float32)
        status_np = np.zeros(num_agents, dtype=np.int32)
        floor_np = np.zeros(num_agents, dtype=np.int32)

        for i, agent in enumerate(agents):
            pos_np[i] = [agent.location.x, agent.location.y, 1.0]
            target_np[i] = [agent.target_x, agent.target_y]
            status_np[i] = agent.infection_status.value
            floor_np[i] = agent.location.floor

        # 2. Push to GPU
        wp_pos = wp.array(pos_np, dtype=wp.vec3)
        wp_targets = wp.array(target_np, dtype=wp.vec2)
        wp_status = wp.array(status_np, dtype=wp.int32)
        wp_floors = wp.array(floor_np, dtype=wp.int32)
        wp_infectors = wp.full(
            num_agents,
            -1,
            dtype=wp.int32,  # type: ignore  # noqa: PGH003
        )  # pyright: ignore[reportArgumentType]

        # 3. Execute Kinematics and Collision
        wp.launch(
            kernel=cuda_warp_kernel_kinematic_agent_movement,
            dim=num_agents,
            inputs=[self.mesh.id, wp_pos, wp_targets, 1.5, 1.0],
        )

        # 4. Execute Transmission Math
        self.grid.build(points=wp_pos, radius=self.search_radius)
        wp.launch(
            kernel=cuda_warp_kernel_agent_proximity,
            dim=num_agents,
            inputs=[
                self.grid.id,
                wp_pos,
                wp_status,
                wp_floors,
                self.search_radius,
                wp_infectors,
            ],
        )
        wp.synchronize()

        # 5. Pull from GPU and update Python state
        new_pos_np = wp_pos.numpy()
        infectors_np = wp_infectors.numpy()

        for i, agent in enumerate(agents):
            # Update Python Brain
            agent.location.x = float(new_pos_np[i][0])
            agent.location.y = float(new_pos_np[i][1])

            # Process Infection
            if infectors_np[i] != -1 and agent.infection_status.value == 0:
                agent.infection_status = agent.infection_status.__class__(2)

                # Record Transmission Event
                source_agent = agents[infectors_np[i]]
                self.transmission_events.append(
                    {
                        "time": self.current_tick,
                        "source_id": source_agent.idx,
                        "target_id": agent.idx,
                        "location_x": agent.location.x,
                        "location_y": agent.location.y,
                    }
                )

            # Record standard telemetry for the Dash Viewer
            self.telemetry.append(
                {
                    "time": self.current_tick,
                    "agent_id": agent.idx,
                    "pos_x": agent.location.x,
                    "pos_y": agent.location.y,
                    "status": agent.infection_status.value,
                }
            )

        self.current_tick += 1

    def export_data(self, output_dir: str = "simulation_outputs") -> None:
        """Save the simulation ledgers to CSV for the Dash Viewer."""
        logger.info("Exporting GPU telemetry to %s...", output_dir)
        out_path: Path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        if self.telemetry:
            df_telemetry = pd.DataFrame(self.telemetry)
            telemetry_path = out_path / "gpu_sim_telemetry.csv"
            df_telemetry.to_csv(telemetry_path, index=False)

        # Build schema to prevent Dash viewer crash if nobody was infected
        cols: list[str] = [
            "time",
            "source_id",
            "target_id",
            "location_x",
            "location_y",
        ]

        if self.transmission_events:
            df_events = pd.DataFrame(self.transmission_events)
            events_path = out_path / "gpu_sim_events.csv"
            df_events.to_csv(events_path, index=False)
        else:
            df_empty = pd.DataFrame(columns=cols)
            empty_path = out_path / "gpu_sim_events.csv"
            df_empty.to_csv(empty_path, index=False)

        logger.info("Export complete")
