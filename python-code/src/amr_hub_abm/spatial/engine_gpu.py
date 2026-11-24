# mypy: ignore-errors
"""
GPU Physics Engine for AMR-Hub.

UCLARC: Nicolin Govender (6/5/26).
Integrates task logic with Warp proposals and HashGrid transmission on CPU/CUDA.
Movement uses float64 proposals and authoritative host-side physical-polygon
validation before accepting any step. This correctness bridge synchronises each
physics tick; it is not a fully device-resident accelerated collision engine.
"""

from __future__ import annotations

import logging
import math
import operator
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import warp as wp

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.spatial.collision import CollisionGeometryCache

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
def warp_kernel_movement_proposals(  # noqa: PLR0913
    positions: wp.array(dtype=wp.vec2d),
    targets: wp.array(dtype=wp.vec2d),
    speeds: wp.array(dtype=wp.float64),
    stochastics: wp.array(dtype=wp.float64),
    radii: wp.array(dtype=wp.float64),
    seed: wp.int32,
    max_attempts: wp.int32,
    proposals: wp.array2d(dtype=wp.vec2d),
) -> None:
    """
    Generate ordered candidates; only the host validator may apply movement.

    All candidates start from the same position. Pre-generating the bounded retry
    sequence does not advance any shared RNG: each thread/tick owns its state.
    The host selects the first valid candidate and ignores the rest.
    """
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

    # Initialize random state for this thread
    state = wp.rand_init(seed, wp.int32(tid))  # pyright: ignore[reportArgumentType]

    # 2. Base direction vector (normalized)
    ndx = wp.float64(0.0)
    ndy = wp.float64(0.0)
    if dist_to_target > radius:
        ndx = dir_x / dist_to_target
        ndy = dir_y / dist_to_target

    for _attempt in range(max_attempts):
        if dist_to_target <= radius or speed == wp.float64(0.0):
            proposals[tid, _attempt] = pos
            continue
        # Apply Stochastic Drift (Trig-Free)
        # Convert stoch (degrees) to a scalar perturbation magnitude (pi/180 ≈ 0.01745)
        drift = wp.float64(wp.randn(state)) * (stoch * wp.float64(0.0174533))

        # Add random perpendicular drift: perpendicular to (ndx, ndy) is (-ndy, ndx)
        vx = ndx - ndy * drift
        vy = ndy + ndx * drift

        # Re-normalize using the known magnitude of the drift (sqrt(1^2 + drift^2))
        v_mag = wp.sqrt(wp.float64(1.0) + drift * drift)

        dx = (vx / v_mag) * speed
        dy = (vy / v_mag) * speed

        # Apply magnitude noise (optional, matching original logic)
        dx = dx * (wp.float64(1.0) + wp.float64(wp.randn(state)) * stoch)
        dy = dy * (wp.float64(1.0) + wp.float64(wp.randn(state)) * stoch)

        # Prevent overshooting the target
        step_dist = wp.sqrt(dx * dx + dy * dy)
        if step_dist >= dist_to_target:
            dx = dir_x
            dy = dir_y

        proposals[tid, _attempt] = wp.vec2d(pos[0] + dx, pos[1] + dy)


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
    if statuses[tid] == 0 and floor_ids[tid] >= 0:  # SUSCEPTIBLE, known context
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
    """
    Hybrid Warp proposal/transmission engine with host collision enforcement.

    Positions and collision geometry remain float64. The float32 HashGrid copy
    is used only for proximity, never for deciding or applying movement. Live
    geometry is prepared once and reused until its source changes; concurrent
    edits during a call are unsupported.
    """

    # ------------------------------------------------------------------------------
    __slots__ = (
        "_collision_geometry",
        "_device",
        "_floor_np",
        # Persistent GPU buffers (allocated once, reused every step to avoid
        # cudaMalloc/cudaFree churn from re-creating wp.array objects per step).
        "_num_agents_cached",
        # Reused host-side staging buffers (avoid re-allocating numpy arrays
        # every tick just to immediately upload and discard them).
        "_pos_np",
        "_proposal_attempts",
        "_radii_np",
        "_speeds_np",
        "_status_np",
        "_stoch_np",
        "_targets_np",
        "_wp_floors",
        "_wp_infectors",
        "_wp_pos",
        "_wp_proposals",
        "_wp_radii",
        "_wp_speeds",
        "_wp_starts",
        "_wp_status",
        "_wp_stoch",
        "_wp_targets",
        "current_tick",  # TimeStep, using 'tick' as the project had that
        "grid",
        "max_movement_attempts",
        "mesh",
        "search_radius",
        "space",
        "telemetry",
        "transmission_events",
    )
    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def __init__(
        self,
        space: Sequence[Building],
        max_movement_attempts: int = 5,
    ) -> None:
        """Bind a Warp device and initialise proposal/proximity storage."""
        logger.info("Initializing hybrid Warp engine with host collision validation")

        self.space = space
        self._device = wp.get_device()
        self.max_movement_attempts = max_movement_attempts
        self._collision_geometry = CollisionGeometryCache(space)

        # ------------------------------------------------------------------------------
        # Retain the legacy centreline mesh for diagnostic compatibility only.
        # It is NOT a collision authority and is never queried by movement.
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
        self.telemetry: list[np.ndarray] = []
        self.transmission_events: list[dict[str, Any]] = []
        self.current_tick: int = 0
        self._num_agents_cached: int = 0
        self._proposal_attempts: int = -1

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    # Done at the start only
    # ------------------------------------------------------------------------------
    def _build_mesh_from_space(self) -> tuple[np.ndarray, np.ndarray]:
        """Build the legacy diagnostic centreline mesh, not physical collision data."""
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
    # Batching loading of data into GPU arrays
    # ------------------------------------------------------------------------------
    def _ensure_gpu_buffers(self, num_agents: int) -> None:
        """
        (Re)allocate persistent GPU + host staging buffers if the agent count changes.

        Allocating a fresh wp.array every tick forces a cudaMalloc/cudaFree
        round-trip per field per step. Since the agent population is fixed for
        the life of a simulation run, we allocate once and reuse the same
        device buffers via `.assign()` (an in-place H2D copy) on every call.
        """
        attempts = max(0, self.max_movement_attempts)
        if (
            num_agents == self._num_agents_cached
            and attempts == self._proposal_attempts
        ):
            return

        self._num_agents_cached = num_agents
        self._proposal_attempts = attempts

        # Host-side staging buffers (reused so we don't re-allocate numpy
        # arrays every tick just to upload and discard them).
        self._pos_np = np.zeros((num_agents, 3), dtype=np.float64)
        self._targets_np = np.zeros((num_agents, 2), dtype=np.float64)
        self._speeds_np = np.zeros(num_agents, dtype=np.float64)
        self._stoch_np = np.zeros(num_agents, dtype=np.float64)
        self._radii_np = np.zeros(num_agents, dtype=np.float64)
        self._status_np = np.zeros(num_agents, dtype=np.int32)
        self._floor_np = np.zeros(num_agents, dtype=np.int32)

        # Device buffers.
        self._wp_pos = wp.zeros(num_agents, dtype=wp.vec3)
        self._wp_starts = wp.zeros(num_agents, dtype=wp.vec2d)
        self._wp_targets = wp.zeros(num_agents, dtype=wp.vec2d)
        self._wp_speeds = wp.zeros(num_agents, dtype=wp.float64)
        self._wp_stoch = wp.zeros(num_agents, dtype=wp.float64)
        self._wp_radii = wp.zeros(num_agents, dtype=wp.float64)
        self._wp_proposals = wp.zeros((num_agents, max(1, attempts)), dtype=wp.vec2d)
        self._wp_status = wp.zeros(num_agents, dtype=wp.int32)
        self._wp_floors = wp.zeros(num_agents, dtype=wp.int32)
        self._wp_infectors = wp.zeros(num_agents, dtype=wp.int32)

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    # Main Function that advances the simulation in time
    # ------------------------------------------------------------------------------
    def is_path_safe(self, agent: Agent, end: tuple[float, float]) -> bool:
        """Check a path against up-to-date prepared geometry for this context."""
        geometry = self._collision_geometry.get_contexts(self.space).get(
            (agent.location.building, agent.location.floor)
        )
        return geometry is not None and geometry.allows(
            (agent.location.x, agent.location.y), end, agent.interaction_radius
        )

    def _validate_physics_inputs(self, agents: list[Agent], batch_steps: int) -> int:
        """Fail before partial batch advancement or unsafe proximity inputs."""
        try:
            batch_steps = operator.index(batch_steps)
        except TypeError as exc:
            msg = "Warp batch steps must be an integer."
            raise SimulationModeError(msg) from exc
        if wp.get_device() != self._device:
            msg = "Warp engine device changed; construct an engine on the new device."
            raise SimulationModeError(msg)
        if not math.isfinite(self.search_radius) or self.search_radius <= 0:
            msg = "Warp proximity search radius must be finite and positive."
            raise SimulationModeError(msg)
        try:
            attempts = operator.index(self.max_movement_attempts)
        except TypeError as exc:
            msg = "Warp movement attempts must be an integer."
            raise SimulationModeError(msg) from exc
        if attempts > np.iinfo(np.int32).max:
            msg = "Warp movement attempts exceed the kernel integer range."
            raise SimulationModeError(msg)
        for agent in agents:
            if not all(
                math.isfinite(v) and abs(v) < np.finfo(np.float32).max
                for v in (agent.location.x, agent.location.y)
            ):
                msg = "Warp requires finite coordinates representable for proximity."
                raise SimulationModeError(msg)
        return batch_steps

    def step_physics(self, agents: list[Agent], batch_steps: int = 1) -> None:
        """
        Validate each physics substep before applying movement or transmission.

        Invalid movement parameters/unknown contexts stay put; nonfinite initial
        positions raise before advancing any agent. Prepared geometry is reused;
        only changed floors are rebuilt before a call advances any agent.
        The engine is bound to its construction device;
        create another engine to change device. Each substep records telemetry
        and infection events exactly as separate one-tick calls would.
        """
        batch_steps = self._validate_physics_inputs(agents, batch_steps)
        if not agents or batch_steps <= 0:
            return
        contexts = self._collision_geometry.get_contexts(self.space)
        context_ids = {key: index for index, key in enumerate(contexts)}
        self._ensure_gpu_buffers(len(agents))
        for _step in range(batch_steps):
            eligible = []
            for i, agent in enumerate(agents):
                self._pos_np[i] = (agent.location.x, agent.location.y, 1.0)
                key = (agent.location.building, agent.location.floor)
                valid = (
                    key in contexts
                    and all(
                        math.isfinite(v)
                        for v in (
                            agent.target_x,
                            agent.target_y,
                            agent.movement_speed,
                            agent.stochasticity,
                            agent.interaction_radius,
                        )
                    )
                    and min(
                        agent.movement_speed,
                        agent.stochasticity,
                        agent.interaction_radius,
                    )
                    >= 0
                )
                eligible.append(valid)
                self._targets_np[i] = (
                    (agent.target_x, agent.target_y)
                    if valid
                    else (agent.location.x, agent.location.y)
                )
                self._speeds_np[i] = agent.movement_speed if valid else 0.0
                self._stoch_np[i] = agent.stochasticity if valid else 0.0
                self._radii_np[i] = agent.interaction_radius if valid else 0.0
                self._status_np[i] = agent.infection_status.value
                self._floor_np[i] = context_ids.get(key, -1)
            self._wp_starts.assign(self._pos_np[:, :2].copy())
            self._wp_targets.assign(self._targets_np)
            self._wp_speeds.assign(self._speeds_np)
            self._wp_stoch.assign(self._stoch_np)
            self._wp_radii.assign(self._radii_np)
            if self._proposal_attempts:
                wp.launch(
                    warp_kernel_movement_proposals,
                    dim=len(agents),
                    inputs=[
                        self._wp_starts,
                        self._wp_targets,
                        self._wp_speeds,
                        self._wp_stoch,
                        self._wp_radii,
                        self.current_tick,
                        self._proposal_attempts,
                        self._wp_proposals,
                    ],
                    device=self._device,
                )
                candidates = self._wp_proposals.numpy()
                for i, agent in enumerate(agents):
                    if not eligible[i]:
                        continue
                    geometry = contexts[(agent.location.building, agent.location.floor)]
                    start = (agent.location.x, agent.location.y)
                    for candidate in candidates[i]:
                        end = (float(candidate[0]), float(candidate[1]))
                        if all(
                            abs(v) < np.finfo(np.float32).max for v in end
                        ) and geometry.allows(start, end, agent.interaction_radius):
                            self._pos_np[i, :2] = end
                            break
            # Rejected proposals never enter this proximity-only float32 copy.
            self._wp_pos.assign(self._pos_np.astype(np.float32))
            self._wp_status.assign(self._status_np)
            self._wp_floors.assign(self._floor_np)
            self._wp_infectors.fill_(-1)
            self.grid.build(points=self._wp_pos, radius=self.search_radius)
            wp.launch(
                cuda_warp_kernel_agent_proximity,
                dim=len(agents),
                inputs=[
                    self.grid.id,
                    self._wp_pos,
                    self._wp_status,
                    self._wp_floors,
                    self.search_radius,
                    self._wp_infectors,
                ],
                device=self._device,
            )
            infectors = self._wp_infectors.numpy()
            self.current_tick += 1
            telemetry = np.empty((len(agents), 5), dtype=np.float64)
            for i, agent in enumerate(agents):
                self.move_to_location(
                    agent,
                    replace(
                        agent.location,
                        x=float(self._pos_np[i, 0]),
                        y=float(self._pos_np[i, 1]),
                    ),
                )
                if infectors[i] != -1 and agent.infection_status.value == 0:
                    agent.infection_status = agent.infection_status.__class__(2)
                    self.transmission_events.append(
                        {
                            "time": self.current_tick,
                            "source_id": agents[infectors[i]].idx,
                            "target_id": agent.idx,
                            "location_x": agent.location.x,
                            "location_y": agent.location.y,
                        }
                    )
                telemetry[i] = (
                    self.current_tick,
                    agent.idx,
                    agent.location.x,
                    agent.location.y,
                    agent.infection_status.value,
                )
            self.telemetry.append(telemetry)
        # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------
    def export_data(self, output_dir: str = "simulation_outputs") -> None:
        """Save the simulation ledgers to CSV for the Dash Viewer."""
        logger.info("Exporting GPU telemetry to %s...", output_dir)
        out_path: Path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        if self.telemetry:
            telemetry_cols = ["time", "agent_id", "pos_x", "pos_y", "status"]
            df_telemetry = pd.DataFrame(
                np.concatenate(self.telemetry, axis=0), columns=telemetry_cols
            )
            df_telemetry["agent_id"] = df_telemetry["agent_id"].astype(int)
            df_telemetry["status"] = df_telemetry["status"].astype(int)
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
