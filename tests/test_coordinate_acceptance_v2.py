import numpy as np
import pytest
from PIL import Image, ImageDraw

from badge_relief_maker.app.core.project_parameters import relief_parameters_from_project
from badge_relief_maker.app.core.project_io import (
    create_project,
    import_image_asset,
    load_project,
    resolve_project_asset,
    save_project,
)
from badge_relief_maker.app.core.project_model import ManualMarker
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief, prepare_relief_field


def _physical_marker_centroid(prepared, width_mm, height_mm):
    affected = prepared.heightmap > 0.8
    assert affected.any()
    rows, cols = prepared.heightmap.shape
    y_indices, x_indices = np.nonzero(affected)
    return (
        float(np.mean((x_indices + 0.5) * (width_mm / cols))),
        float(np.mean((y_indices + 0.5) * (height_mm / rows))),
        width_mm / cols,
        height_mm / rows,
    )


def test_saved_project_coordinate_chain_is_stable_across_quality_modes(tmp_path):
    """Exercise perspective, crop, mask, final-grid edits and save/reopen as one fixture."""
    source_path = tmp_path / "perspective-coordinate-source.png"
    image = Image.new("RGBA", (240, 180), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((45, 32, 198, 148), radius=12, fill=(96, 96, 96, 255))
    image.save(source_path)

    project = create_project("Coordinate Acceptance")
    project.dimensions.width_mm = 80.0
    project.dimensions.height_mm = 60.0
    project.front_relief.mask_mode = "alpha"
    project.front_relief.height_mode = "layers"
    project.front_relief.background_depth_mm = 0.0
    project.front_relief.perspective_quad = [
        [0.04, 0.06],
        [0.96, 0.03],
        [0.93, 0.96],
        [0.08, 0.93],
    ]
    project.front_relief.manual_crop_box = [5, 5, 210, 155]
    project.front_relief.mask_edits = [
        {
            "operation": "remove",
            "coordinate_space": "normalized",
            "x": 0.72,
            "y": 0.30,
            "radius_normalized": 0.035,
        }
    ]
    project.front_relief.region_layers = [
        {
            "coordinate_space": "final_normalized",
            "x": 0.68,
            "y": 0.68,
            "radius_normalized": 0.04,
            "height_normalized": 0.25,
            "locked": True,
        }
    ]
    project.manual_markers.append(
        ManualMarker(
            marker_type="height",
            target="front",
            data={
                "operation": "set",
                "coordinate_space": "final_normalized",
                "x": 0.30,
                "y": 0.65,
                "radius_normalized": 0.04,
                "height_normalized": 1.0,
            },
        )
    )

    project_path = tmp_path / "coordinate-acceptance.medalproj"
    save_project(project, project_path)
    import_image_asset(project, project_path, source_path, "front")
    save_project(project, project_path)

    reopened = load_project(project_path)
    assert reopened.front_relief.perspective_quad == project.front_relief.perspective_quad
    assert reopened.front_relief.manual_crop_box == project.front_relief.manual_crop_box
    assert reopened.front_relief.mask_edits == project.front_relief.mask_edits
    assert reopened.front_relief.region_layers == project.front_relief.region_layers
    assert reopened.manual_markers[0].data == project.manual_markers[0].data
    imported_source = resolve_project_asset(project_path, reopened.front_image.path)

    centroids = []
    for quality_mode in ("preview", "standard", "high"):
        parameters, resolved_quality = relief_parameters_from_project(
            reopened,
            side_name="front",
            quality_mode=quality_mode,
        )
        assert resolved_quality == quality_mode
        prepared = prepare_relief_field(imported_source, parameters)
        result = build_single_side_relief(imported_source, parameters=parameters)

        assert prepared.report["image_source"]["perspective"]["source_quad_normalized"]
        assert prepared.report["manual_crop_box"] == (5, 5, 210, 155)
        assert prepared.report["crop_box"] is not None
        assert prepared.report["geometry_crop_box"] is not None
        assert prepared.report["mask_edits"]["applied_edit_count"] == 1
        assert prepared.report["region_layers"]["applied_layer_count"] == 1
        assert prepared.report["manual_height"]["applied_marker_count"] == 1
        assert result.report["bbox"]["size_x"] == pytest.approx(80.0, abs=0.05)
        assert result.report["bbox"]["size_y"] == pytest.approx(60.0, abs=0.05)
        centroids.append(_physical_marker_centroid(prepared, 80.0, 60.0))

    expected_x = 0.30 * 80.0
    expected_y = 0.65 * 60.0
    for x_mm, y_mm, cell_w, cell_h in centroids:
        assert x_mm == pytest.approx(expected_x, abs=cell_w)
        assert y_mm == pytest.approx(expected_y, abs=cell_h)

    for first in centroids:
        for second in centroids:
            assert abs(first[0] - second[0]) <= max(first[2], second[2])
            assert abs(first[1] - second[1]) <= max(first[3], second[3])
