import numpy as np
import pytest
from PIL import Image

from badge_relief_maker.app.core.quality_modes import quality_preset
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import prepare_relief_field


def _physical_centroid(prepared, width_mm, height_mm):
    affected = prepared.heightmap > 0.5
    assert affected.any()
    rows, cols = prepared.heightmap.shape
    y_indices, x_indices = np.nonzero(affected)
    x_mm = float(np.mean((x_indices + 0.5) * (width_mm / cols)))
    y_mm = float(np.mean((y_indices + 0.5) * (height_mm / rows)))
    return x_mm, y_mm, width_mm / cols, height_mm / rows


def test_final_normalized_edit_stays_in_same_physical_region_across_quality_modes(tmp_path):
    image = Image.new("RGBA", (200, 160), (0, 0, 0, 0))
    for y in range(10, 150):
        for x in range(15, 185):
            image.putpixel((x, y), (128, 128, 128, 255))
    image_path = tmp_path / "coordinate-fixture.png"
    image.save(image_path)

    width_mm = 80.0
    height_mm = 60.0
    centroids = []
    for mode in ("preview", "standard", "high"):
        preset = quality_preset(mode)
        prepared = prepare_relief_field(
            image_path,
            ReliefParameters(
                width_mm=width_mm,
                height_mm=height_mm,
                mask_mode="alpha",
                uniform_height_normalized=0.0,
                max_grid_cells=preset["max_grid_cells"],
                min_component_pixels=preset["min_component_pixels"],
                fill_hole_pixels=preset["fill_hole_pixels"],
                mask_smooth_iterations=preset["mask_smooth_iterations"],
                manual_height_markers=(
                    {
                        "marker_type": "height",
                        "target": "front",
                        "shape": "circle",
                        "coordinate_space": "final_normalized",
                        "x": 0.3,
                        "y": 0.65,
                        "radius_normalized": 0.04,
                        "operation": "set",
                        "height_normalized": 1.0,
                    },
                ),
            ),
        )
        centroids.append(_physical_centroid(prepared, width_mm, height_mm))
        assert prepared.report["manual_height"]["applied_marker_count"] == 1

    expected_x = 0.3 * width_mm
    expected_y = 0.65 * height_mm
    for x_mm, y_mm, cell_w, cell_h in centroids:
        assert x_mm == pytest.approx(expected_x, abs=cell_w)
        assert y_mm == pytest.approx(expected_y, abs=cell_h)

    for first in centroids:
        for second in centroids:
            tolerance_x = max(first[2], second[2])
            tolerance_y = max(first[3], second[3])
            assert abs(first[0] - second[0]) <= tolerance_x
            assert abs(first[1] - second[1]) <= tolerance_y
