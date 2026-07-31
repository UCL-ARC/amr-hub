# mypy: ignore-errors
"""
GPU Physics Engine for AMR-Hub.

UCLARC: Nicolin Govender (6/5/26).
Integrates existing CPU logic (Tasks/Agents/SpatialQueries) with GPU (CUDA Warp).
Calculates HashGrid transmission, executes BVH spatial queries, handles stochastic
movement, and batches execution to eliminate PCIe transfer bottlenecks.
"""

from __future__ import annotations

import logging
import math
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import warp as wp

if TYPE_CHECKING:
    from collections.abc import Sequence

    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.spatial.building import Building
    from amr_hub_abm.spatial.location import Location
    from amr_hub_abm.spatial.room import Room

# Setup standard logger
logger = logging.getLogger(__name__)

# =============================================================================
# Call the GPU Driver
wp.init()
# =============================================================================


# =============================================================================
# A] Agent moves in space (Target-Based Steering and Single Collision)
# One thread per agent
# =============================================================================
@wp.kernel
def cuda_warp_kernel_kinematic_agent_movement(  # noqa: PLR0913
    mesh: wp.uint64,
    positions: wp.array(dtype=wp.vec3),
    targets: wp.array(dtype=wp.vec2),
    speeds: wp.array(dtype=float),
    stochastics: wp.array(dtype=float),
    radii: wp.array(dtype=float),
    seed: wp.int32,
) -> None:
    """Calculate target-based steering and stochastic movement."""
    tid = wp.tid()
    pos = positions[tid]
    target = targets[tid]
    speed = speeds[tid]
    stoch = stochastics[tid]
    radius = radii[tid]

    # 1. Calculate vector to target
    dir_x = target[0] - pos[0]
    dir_y = target[1] - pos[1]
    dist_to_target = wp.sqrt(dir_x * dir_x + dir_y * dir_y)

    # If already within interaction radius, don't move
    if dist_to_target <= radius:
        return

    # Initialize random state for this thread
    state = wp.rand_init(seed, wp.int32(tid))  # pyright: ignore[reportArgumentType]

    # 2. Base direction vector (normalized)
    ndx = dir_x / dist_to_target
    ndy = dir_y / dist_to_target

    # 3. Apply Stochastic Drift (Trig-Free)
    # Convert stoch (degrees) to a scalar perturbation magnitude (pi/180 ≈ 0.01745)
    drift = wp.randn(state) * (stoch * 0.0174533)

    # Add random perpendicular drift: perpendicular to (ndx, ndy) is (-ndy, ndx)
    vx = ndx - ndy * drift
    vy = ndy + ndx * drift

    # Re-normalize using the known magnitude of the drift (sqrt(1^2 + drift^2))
    v_mag = wp.sqrt(1.0 + drift * drift)

    dx = (vx / v_mag) * speed
    dy = (vy / v_mag) * speed

    # Apply magnitude noise (optional, matching original logic)
    dx = dx * (1.0 + wp.randn(state) * stoch)
    dy = dy * (1.0 + wp.randn(state) * stoch)

    # Prevent overshooting the target
    step_dist = wp.sqrt(dx * dx + dy * dy)
    if step_dist > dist_to_target:
        dx = dir_x
        dy = dir_y

    next_pos = wp.vec3(pos[0] + dx, pos[1] + dy, pos[2])

    # 4. Single BVH Collision Check against walls
    ray_dir = wp.normalize(next_pos - pos)
    step_size = wp.length(next_pos - pos)

    root = wp.int32(0)
    hit = wp.mesh_query_ray(mesh, pos, ray_dir, step_size, root)

    if not hit.result:  # pyright: ignore[reportAttributeAccessIssue]
        # Valid move, apply immediately
        positions[tid] = next_pos


# =============================================================================


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


# =============================================================================
# C] Python-to-GPU Engine Class
# =============================================================================
class GPUSpatialQuery:
    """Manages the Warp GPU state for the sim, mimics CPU spatial queries."""

    __slots__ = (
        "current_tick",  # TimeStep, using tick as the project had that
        "grid",
        "max_movement_attempts",
        "mesh",
        "search_radius",
        "space",
        "telemetry",
        "transmission_events",
    )

    # ------------------------------------------------------------------------------
    def __init__(
        self,
        space: Sequence[Building],
        max_movement_attempts: int = 5,
    ) -> None:
        """Init GPU engine, dynamically generating the BVH mesh from floor plans."""
        logger.info("Initializing GPU Spatial Engine from Polygons")

        self.space = space
        self.max_movement_attempts = max_movement_attempts

        # ------------------------------------------------------------------------------
        # Extract live geometry from the Space objects
        # ------------------------------------------------------------------------------
        wall_vertices, wall_indices = self._build_mesh_from_space()
        logger.info(
            f"Generated GPU Mesh: {len(wall_vertices)} vertices, {len(wall_indices) // 3} faces"  # noqa: E501, G004
        )

        self.mesh: wp.Mesh = wp.Mesh(
            points=wp.array(wall_vertices, dtype=wp.vec3),
            indices=wp.array(wall_indices, dtype=wp.int32),
        )
        self.grid: wp.HashGrid = wp.HashGrid(dim_x=128, dim_y=128, dim_z=128)
        self.search_radius: float = 2.0
        self.telemetry: list[dict[str, Any]] = []
        self.transmission_events: list[dict[str, Any]] = []
        self.current_tick: int = 0

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    # Done at the start only
    # ------------------------------------------------------------------------------
    def _build_mesh_from_space(self) -> tuple[np.ndarray, np.ndarray]:
        """Convert 2D room walls into a 3D GPU collision mesh."""
        vertices = []
        indices = []
        v_idx = 0

        for building in self.space:
            for floor in building.floors:
                for room in floor.rooms:
                    # Skip rooms that don't have physical walls defined yet
                    if not room.walls:
                        continue

                    for wall in room.walls:
                        # Grab the explicit start and end tuples from the Wall object
                        x1, y1 = wall.start
                        x2, y2 = wall.end

                        # Extrude 2D line segment into a 3D vertical quad (Z: -1 to 3 m)
                        vertices.extend(
                            [
                                [x1, y1, -1.0],  # Bottom Left
                                [x2, y2, -1.0],  # Bottom Right
                                [x2, y2, 3.0],  # Top Right
                                [x1, y1, 3.0],  # Top Left
                            ]
                        )

                        # Triangle 1 (0, 1, 2)
                        indices.extend([v_idx, v_idx + 1, v_idx + 2])
                        # Triangle 2 (0, 2, 3)
                        indices.extend([v_idx, v_idx + 2, v_idx + 3])

                        v_idx += 4

        # Return as strongly-typed numpy arrays for Warp
        return np.array(vertices, dtype=np.float32), np.array(indices, dtype=np.int32)

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    # Mimic CPU Engine
    # ------------------------------------------------------------------------------
    def get_room(
        self,
        agent: Agent,
        coords: tuple[float, float] | None = None,
    ) -> Room | None:
        """Find the room containing the agent or specific coords."""
        if agent.location.building is None or agent.location.floor is None:
            return None

        check_coords = (
            coords if coords is not None else (agent.location.x, agent.location.y)
        )

        for building in self.space:
            if building.name != agent.location.building:
                continue
            for floor in building.floors:
                if floor.floor_number != agent.location.floor:
                    continue
                room = floor.find_room_by_location(check_coords)
                if room:
                    return room
        return None

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def move_one_step(self, agent: Agent) -> None:
        """
        Defer physical movement for the agent.

        The CPU calls this to move the agent, but in GPU mode,
        we defer all physical movement until step_physics() processes the bulk batch.
        """

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def is_target_reached(
        self,
        location: Location,
        target: Location,
        radius: float,
    ) -> bool:
        """Check whether *location* is within *radius* of *target*."""
        if location.building != target.building:
            return False
        if location.floor != target.floor:
            return False
        return location.distance_to(target) <= radius

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def estimate_time_to_reach_location(
        self, agent: Agent, target_location: Location
    ) -> float:
        """Estimate the time required to reach a target location."""
        return agent.location.distance_to(target_location) / agent.movement_speed

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def move_to_location(self, agent: Agent, new_location: Location) -> None:
        """Move the agent to a new location."""
        agent.location = new_location

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def head_to_point(self, agent: Agent, point: tuple[float, float]) -> None:
        """Set the agent's target coordinates so the GPU can steer it(CPU)."""
        delta_x = point[0] - agent.location.x
        delta_y = point[1] - agent.location.y
        agent.heading_rad = math.atan2(delta_y, delta_x) % (2 * math.pi)

        # Pass the target destination to the agent so it syncs with the GPU
        agent.target_x = point[0]
        agent.target_y = point[1]

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    # Main Function that advances the simulation in time
    # ------------------------------------------------------------------------------
    def step_physics(self, agents: list[Any], batch_steps: int = 1) -> None:
        """Sync state, push to GPU, batch time steps."""
        num_agents = len(agents)
        if num_agents == 0:
            return

        # 1. Extract Python state to NumPy (done ONCE)
        pos_np = np.zeros((num_agents, 3), dtype=np.float32)
        targets_np = np.zeros((num_agents, 2), dtype=np.float32)
        speeds_np = np.zeros(num_agents, dtype=np.float64)
        stoch_np = np.zeros(num_agents, dtype=np.float64)
        radii_np = np.zeros(num_agents, dtype=np.float64)
        status_np = np.zeros(num_agents, dtype=np.int32)
        floor_np = np.zeros(num_agents, dtype=np.int32)

        for i, agent in enumerate(agents):
            pos_np[i] = [agent.location.x, agent.location.y, 1.0]  # Agent sits at Z=1.0
            targets_np[i] = [agent.target_x, agent.target_y]
            speeds_np[i] = agent.movement_speed
            stoch_np[i] = agent.stochasticity
            radii_np[i] = agent.interaction_radius
            status_np[i] = agent.infection_status.value
            floor_np[i] = agent.location.floor

        # 2. Push to GPU (done ONCE)
        wp_pos = wp.array(pos_np, dtype=wp.vec3)
        wp_targets = wp.array(targets_np, dtype=wp.vec2)
        wp_speeds = wp.array(speeds_np, dtype=float)
        wp_stoch = wp.array(stoch_np, dtype=float)
        wp_radii = wp.array(radii_np, dtype=float)
        wp_status = wp.array(status_np, dtype=wp.int32)
        wp_floors = wp.array(floor_np, dtype=wp.int32)
        wp_infectors = wp.full(
            num_agents,
            -1,
            dtype=wp.int32,  # type: ignore  # noqa: PGH003
        )  # pyright: ignore[reportArgumentType]

        # 3. Batch Loop (Eliminates PCIe Roundtrips)
        for _step in range(batch_steps):
            seed = self.current_tick

            # A) Execute Target-Based Kinematics
            wp.launch(
                kernel=cuda_warp_kernel_kinematic_agent_movement,
                dim=num_agents,
                inputs=[
                    self.mesh.id,
                    wp_pos,
                    wp_targets,
                    wp_speeds,
                    wp_stoch,
                    wp_radii,
                    seed,
                ],
            )

            # B) Execute Transmission Math
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

            # C) Wait for GPU to finish this micro-tick
            wp.synchronize()
            self.current_tick += 1

        # 4. Pull from GPU (done ONCE at the end of the batch)
        new_pos_np = wp_pos.numpy()
        infectors_np = wp_infectors.numpy()

        for i, agent in enumerate(agents):
            # Update Python Brain using move_to_location for parity
            new_loc = replace(
                agent.location, x=float(new_pos_np[i][0]), y=float(new_pos_np[i][1])
            )
            self.move_to_location(agent, new_loc)

            # Process Infection
            if infectors_np[i] != -1 and agent.infection_status.value == 0:
                agent.infection_status = agent.infection_status.__class__(2)

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

            # Record batched telemetry for the Dash Viewer
            self.telemetry.append(
                {
                    "time": self.current_tick,
                    "agent_id": agent.idx,
                    "pos_x": agent.location.x,
                    "pos_y": agent.location.y,
                    "status": agent.infection_status.value,
                }
            )

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def export_data(self, output_dir: str = "simulation_outputs") -> None:
        """Save the simulation ledgers to CSV for the Dash Viewer."""
        logger.info("Exporting GPU telemetry to %s...", output_dir)
        out_path: Path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        if self.telemetry:
            df_telemetry = pd.DataFrame(self.telemetry)
            telemetry_path = out_path / "gpu_sim_telemetry.csv"
            df_telemetry.to_csv(telemetry_path, index=False)

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

    # ------------------------------------------------------------------------------


# =============================================================================
