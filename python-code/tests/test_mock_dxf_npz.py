"""Unit tests for mock DXF generation and NPZ environment viewing."""

from pathlib import Path
from typing import Any, cast

import numpy as np

from floorplan_extractor_python.mock_dfx_gen import generate_complex_hospital
from floorplan_extractor_python.mock_npz_view import query_environment


def test_generate_complex_hospital_creates_dxf(tmp_path: Path) -> None:
    """Ensure the mock hospital layout generates a valid DXF file structure."""
    output_dxf: Path = tmp_path / "TestFloorPlan.dxf"

    # Execute generator with our temporary path string
    generate_complex_hospital(filename=str(output_dxf))

    # Assert file creation
    assert output_dxf.exists(), "The generator failed to write the DXF file!"
    assert output_dxf.stat().st_size > 0, "Generated DXF file is empty!"


def test_query_environment_bvh_logic() -> None:
    """Verify brute force spatial queries resolve rooms and nearest beds."""
    # 1. Create a mock NPZ file mapping structured as an NpzFile container
    mock_room_coords: np.ndarray = np.array(
        [[10.0, 2.5], [5.0, 10.0], [15.0, 10.0]], dtype=np.float32
    )
    mock_room_names: np.ndarray = np.array(
        ["CORRIDOR", "ICU_WARD", "STD_WARD"], dtype=object
    )
    # Beds stored as bounding box coordinates [min_x, min_y, max_x, max_y]
    mock_beds: np.ndarray = np.array(
        [[1.0, 12.0, 3.0, 14.0], [11.0, 12.0, 13.0, 14.0]], dtype=np.float32
    )

    # Build an in-memory dictionary acting like the loaded NPZ structure
    mock_npz_data: dict[str, np.ndarray] = {
        "room_coords": mock_room_coords,
        "room_names": mock_room_names,
        "beds": mock_beds,
    }

    # 2. Simulate an agent position inside the ICU Ward (near Bed 1 at center 2,13)
    agent_pos: tuple[float, float, float] = (2.0, 13.0, 1.0)

    # 3. Execute query function under test
    current_room, closest_bed = query_environment(agent_pos, cast("Any", mock_npz_data))

    # 4. Spatial Assertions
    assert current_room == "ICU_WARD", "Agent should be closest to ICU_WARD!"
    assert closest_bed == 1, "Agent should be closest to Bed 1!"
