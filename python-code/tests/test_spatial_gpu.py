"""Unit tests for the CUDA Warp-accelerated GPU Physics Engine."""

import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Note: Adjust the import path if needed
from amr_hub_abm.spatial.engine_gpu import GPUSpatialQuery


@pytest.fixture
def mock_engine() -> GPUSpatialQuery:
    """Fixture to provide a patched GPU engine instance with an empty space."""
    with patch("warp.init"), patch("warp.Mesh"), patch("warp.HashGrid"):
        return GPUSpatialQuery(space=[], max_movement_attempts=5)


# ------------------------------------------------------------------------------
# 1. Initialization and Export Tests
# ------------------------------------------------------------------------------
def test_gpu_physics_engine_initialization(tmp_path: Path) -> None:
    """Verify that the physics engine maps and exports state tables cleanly."""
    with patch("warp.init"), patch("warp.Mesh"), patch("warp.HashGrid"):
        engine = GPUSpatialQuery(space=[])

    # Assert initialization variables are structurally sound
    assert engine.current_tick == 0
    assert engine.search_radius == 2.0
    assert isinstance(engine.telemetry, list)

    # Add mock telemetry records to validate the pandas export step
    engine.telemetry.append(
        {"time": 0, "agent_id": "A1", "pos_x": 1.5, "pos_y": 2.5, "status": 0}
    )

    output_dir: Path = tmp_path / "sim_outputs"
    engine.export_data(output_dir=str(output_dir))

    # Verify ledger files were physically populated
    assert (output_dir / "gpu_sim_telemetry.csv").exists()
    assert (output_dir / "gpu_sim_events.csv").exists()


def test_build_mesh_from_space() -> None:
    """Verify that 2D walls are correctly extruded into a 3D Warp mesh."""
    # Setup mock hierarchy mimicking Building -> Floor -> Room -> Wall
    mock_wall = MagicMock()
    mock_wall.start = (0.0, 0.0)
    mock_wall.end = (10.0, 0.0)

    mock_room = MagicMock()
    mock_room.walls = [mock_wall]

    mock_floor = MagicMock()
    mock_floor.rooms = [mock_room]

    mock_building = MagicMock()
    mock_building.floors = [mock_floor]

    with patch("warp.init"), patch("warp.Mesh"), patch("warp.HashGrid"):
        # The init function calls _build_mesh_from_space internally
        engine = GPUSpatialQuery(space=[mock_building])

    vertices, indices = engine._build_mesh_from_space()  # noqa: SLF001

    # 1 wall = 1 quad = 4 vertices and 2 triangles (6 indices)
    assert len(vertices) == 4
    assert len(indices) == 6

    # Verify the vertical (Z) extrusion bounds
    assert vertices[0][2] == -1.0  # Bottom Z
    assert vertices[2][2] == 3.0  # Top Z

    # Verify X and Y were mapped correctly
    assert vertices[0][0] == 0.0  # x1
    assert vertices[1][0] == 10.0  # x2


# ------------------------------------------------------------------------------
# 2. CPU-Parity API Tests
# ------------------------------------------------------------------------------
def test_is_target_reached(mock_engine: GPUSpatialQuery) -> None:
    """Test distance evaluation and building/floor matching constraints."""
    loc1 = MagicMock()
    loc1.building = "UCL_Main"
    loc1.floor = 1

    loc2 = MagicMock()
    loc2.building = "UCL_Main"
    loc2.floor = 1

    # Distance is within radius
    loc1.distance_to.return_value = 1.0
    assert mock_engine.is_target_reached(loc1, loc2, radius=2.0) is True

    # Distance is outside radius
    loc1.distance_to.return_value = 3.0
    assert mock_engine.is_target_reached(loc1, loc2, radius=2.0) is False

    # Different floor
    loc3 = MagicMock()
    loc3.building = "UCL_Main"
    loc3.floor = 2
    assert mock_engine.is_target_reached(loc1, loc3, radius=5.0) is False

    # Different building
    loc4 = MagicMock()
    loc4.building = "UCL_East"
    loc4.floor = 1
    assert mock_engine.is_target_reached(loc1, loc4, radius=5.0) is False


def test_estimate_time_to_reach_location(mock_engine: GPUSpatialQuery) -> None:
    """Verify standard kinematic time calculations."""
    agent = MagicMock()
    agent.movement_speed = 2.0
    target_loc = MagicMock()

    # Distance is 10, speed is 2, time should be 5
    agent.location.distance_to.return_value = 10.0

    time_est = mock_engine.estimate_time_to_reach_location(agent, target_loc)
    assert time_est == 5.0


def test_move_to_location(mock_engine: GPUSpatialQuery) -> None:
    """Verify that moving an agent assigns the exact new location object."""
    agent = MagicMock()
    new_loc = MagicMock()

    mock_engine.move_to_location(agent, new_loc)
    assert agent.location == new_loc


def test_head_to_point(mock_engine: GPUSpatialQuery) -> None:
    """Verify heading is correctly calculated using arctan2."""
    agent = MagicMock()
    agent.location.x = 0.0
    agent.location.y = 0.0

    # Point is directly up (+y axis), should be Pi/2 radians
    mock_engine.head_to_point(agent, (0.0, 1.0))
    assert math.isclose(agent.heading_rad, math.pi / 2)

    # Point is directly left (-x axis), should be Pi radians
    mock_engine.head_to_point(agent, (-1.0, 0.0))
    assert math.isclose(agent.heading_rad, math.pi)


def test_get_room(mock_engine: GPUSpatialQuery) -> None:
    """Test spatial traversal to find correct rooms based on coordinates."""
    # Setup mock room
    mock_room = MagicMock()
    mock_room.name = "Room_101"

    # Setup mock floor
    mock_floor = MagicMock()
    mock_floor.floor_number = 1
    mock_floor.find_room_by_location.return_value = mock_room

    # Setup mock building
    mock_building = MagicMock()
    mock_building.name = "Building_A"
    mock_building.floors = [mock_floor]

    # Assign to engine (ignore Pylance's list invariance warning for mocks)
    mock_engine.space = [mock_building]  # pyright: ignore[reportAttributeAccessIssue, reportAssignmentType]

    # Setup mock agent
    agent = MagicMock()
    agent.location.building = "Building_A"
    agent.location.floor = 1
    agent.location.x = 5.0
    agent.location.y = 5.0

    # 1. Test using agent's implicit coordinates
    room = mock_engine.get_room(agent)
    mock_floor.find_room_by_location.assert_called_with((5.0, 5.0))
    assert room == mock_room

    # 2. Test using explicit coordinates
    room_explicit = mock_engine.get_room(agent, coords=(10.0, 10.0))
    mock_floor.find_room_by_location.assert_called_with((10.0, 10.0))
    assert room_explicit == mock_room

    # 3. Test missing building
    agent.location.building = "Building_B"
    assert mock_engine.get_room(agent) is None
