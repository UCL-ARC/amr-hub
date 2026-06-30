"""Unit tests for the DXF layout compiler and extractor."""

from pathlib import Path

import numpy as np

# Explicitly import the compiler function
from floorplan_extractor_python.convertor_dxf_npz_yaml import compile_semantic_dxf


def test_compile_semantic_dxf_regression(tmp_path: Path) -> None:
    """Ensure the compiler extracts entities and builds outputs successfully."""
    # 1. Point to your consolidated test inputs
    mock_dxf_file = Path("tests/inputs/GPU_FloorPlan.dxf")

    output_npz = tmp_path / "test_output.npz"
    output_yaml = tmp_path / "test_output.yml"

    # 2. Execute the function
    compile_semantic_dxf(str(mock_dxf_file), str(output_npz), str(output_yaml))

    # 3. Assertions
    assert output_npz.exists(), "The compiler failed to generate the .npz array!"
    assert output_yaml.exists(), "The compiler failed to generate the structural .yml!"

    # 4. Verify data contents
    data = np.load(str(output_npz), allow_pickle=True)
    assert "wall_vertices" in data
    assert len(data["wall_vertices"]) > 0
