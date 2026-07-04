"""Unit tests for the CUDA Warp-accelerated GPU Physics Engine."""

from pathlib import Path
from unittest.mock import patch

import numpy as np

from amr_hub_abm.gpu_physics import GPUPhysicsEngine


def test_gpu_physics_engine_initialization(tmp_path: Path) -> None:
    """Verify that the physics engine maps and exports state tables cleanly."""
    # 1. Create a dummy .npz file so the initializer can load real geometry keys
    dummy_npz: Path = tmp_path / "floorplan_simple_a.npz"
    np.savez(
        str(dummy_npz),
        wall_vertices=np.array([[0.0, 0.0, 0.0]], dtype=np.float32),
        wall_indices=np.array([0], dtype=np.int32),
    )

    # 2. Patch Warp dependencies inline to prevent unused argument warnings
    with (
        patch("warp.init"),
        patch("warp.Mesh"),
        patch("warp.HashGrid"),
    ):
        engine = GPUPhysicsEngine(cad_path=str(dummy_npz))

    # Assert initialization variables are structurally sound
    assert engine.current_tick == 0
    assert engine.search_radius == 2.0
    assert isinstance(engine.telemetry, list)

    # 3. Add mock telemetry records to validate the pandas export step
    engine.telemetry.append(
        {"time": 0, "agent_id": "A1", "pos_x": 1.5, "pos_y": 2.5, "status": 0}
    )

    output_dir: Path = tmp_path / "sim_outputs"
    engine.export_data(output_dir=str(output_dir))

    # Verify ledger files were physically populated
    assert (output_dir / "gpu_sim_telemetry.csv").exists()
    assert (output_dir / "gpu_sim_events.csv").exists()
