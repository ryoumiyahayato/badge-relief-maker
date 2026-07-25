from pathlib import Path

import numpy as np
from PIL import Image

from badge_relief_maker.app.core.approved_heightmap_builder import build_relief_from_approved_heightmap
from badge_relief_maker.app.core.relief_parameters import ReliefParameters


def test_approved_16bit_heightmap_builds_closed_editable_obj(tmp_path):
    yy, xx = np.mgrid[:64, :48]
    mask = ((xx - 24) / 18.0) ** 2 + ((yy - 32) / 27.0) ** 2 <= 1.0
    height = np.zeros((64, 48), dtype=np.float32)
    height[mask] = 0.25 + 0.65 * (
        1.0 - np.sqrt(np.clip(((xx[mask] - 24) / 18.0) ** 2 + ((yy[mask] - 32) / 27.0) ** 2, 0.0, 1.0))
    )
    height_path = tmp_path / "approved.png"
    mask_path = tmp_path / "solid.png"
    output_path = tmp_path / "approved.obj"
    Image.fromarray(np.round(height * 65535.0).astype(np.uint16)).save(height_path)
    Image.fromarray((mask * 255).astype(np.uint8), mode="L").save(mask_path)

    result = build_relief_from_approved_heightmap(
        height_path,
        output_path,
        mask_path=mask_path,
        parameters=ReliefParameters(
            width_mm=60.0,
            height_mm=80.0,
            base_thickness_mm=2.0,
            relief_height_mm=4.0,
            max_grid_cells=10000,
        ),
    )

    assert Path(result.output_path).is_file()
    assert result.report["source_of_truth"] == "approved grayscale height master"
    assert result.report["automatic_height_synthesis"] is False
    assert result.report["bbox"]["size_z"] > 5.0
    assert result.report["topology"]["boundary_edge_count"] == 0
    assert result.report["topology"]["non_manifold_edge_count"] == 0
    assert result.report["editable_surface_groups"]["flat_back"] > 0
