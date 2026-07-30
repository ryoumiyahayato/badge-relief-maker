import json

import numpy as np
import pytest
from PIL import Image

from badge_relief_maker.app.core.image_transform import ImageTransform
from badge_relief_maker.app.core.manufacturability_check import basic_report
from badge_relief_maker.app.core.marker_transform import transform_manual_height_markers
from badge_relief_maker.app.core.mask_generator import foreground_mask
from badge_relief_maker.app.core.mesh_exporter import export_obj
from badge_relief_maker.app.core.project_parameters import map_project_relief_parameters
from badge_relief_maker.app.core.project_io import (
    UnsupportedProjectVersionError,
    create_project,
    load_project,
    resolve_project_asset,
    save_project,
)
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief


def test_image_transform_maps_points_dimensions_and_geometry_crop():
    transform = ImageTransform(
        original_shape=(100, 200),
        crop_box=(20, 10, 180, 90),
        cropped_shape=(80, 160),
        resized_shape=(40, 80),
    )

    x, y = transform.original_to_processed_point(0.5, 0.5, normalized=True)
    assert x == pytest.approx(39.5)
    assert y == pytest.approx(19.5)
    assert transform.original_radius_to_processed(10, normalized=False) == pytest.approx(5.0)
    assert transform.original_length_to_processed(0.25, "x", normalized=True) == pytest.approx(24.875)

    final_transform = transform.with_geometry_crop((5, 3, 75, 37), (34, 70))
    assert final_transform.original_to_target_point(0.5, 0.5, normalized=True) == pytest.approx((34.5, 16.5))
    assert final_transform.processed_to_geometry_point(x, y) == pytest.approx((34.5, 16.5))
    assert final_transform.input_grid_to_target_point(12, 8, "processed") == pytest.approx((7.0, 5.0))
    assert final_transform.input_grid_to_target_point(12, 8, "final") == pytest.approx((12.0, 8.0))
    assert final_transform.geometry_cell_size_mm(80.0, 60.0) == pytest.approx((80.0 / 70.0, 60.0 / 34.0))
    assert final_transform.to_report()["coordinate_chain"].startswith("original_image")


def test_marker_transform_accepts_shared_image_transform():
    transform = ImageTransform(
        original_shape=(100, 200),
        crop_box=(20, 10, 180, 90),
        cropped_shape=(80, 160),
        resized_shape=(40, 80),
    )
    markers = transform_manual_height_markers(
        {"marker_type": "height", "x": 100, "y": 50, "radius_px": 10, "height": 0.5, "coordinate_space": "pixel"},
        image_transform=transform,
    )

    assert len(markers) == 1
    assert markers[0]["x"] == pytest.approx(80.0 * 79.0 / 159.0)
    assert markers[0]["y"] == pytest.approx(40.0 * 39.0 / 79.0)
    assert markers[0]["radius_px"] == pytest.approx(5.0)


def test_marker_transform_shifts_processed_but_not_final_coordinates():
    transform = ImageTransform(
        original_shape=(20, 20),
        crop_box=None,
        cropped_shape=(20, 20),
        resized_shape=(20, 20),
        geometry_crop_box=(4, 3, 16, 17),
        geometry_shape=(14, 12),
    )
    processed, final = transform_manual_height_markers(
        (
            {"marker_type": "height", "x": 9, "y": 8, "height": 0.5, "coordinate_space": "processed"},
            {"marker_type": "height", "x": 9, "y": 8, "height": 0.5, "coordinate_space": "final"},
        ),
        image_transform=transform,
    )

    assert (processed["x"], processed["y"]) == pytest.approx((5.0, 5.0))
    assert (final["x"], final["y"]) == pytest.approx((9.0, 8.0))


def test_explicit_luminance_polarities_select_expected_foreground():
    light_background = np.full((5, 5, 4), 255, dtype=np.uint8)
    light_background[2, 2, :3] = 0
    dark_mask, dark_mode = foreground_mask(light_background, mode="luminance-dark", luminance_threshold=20)

    dark_background = np.zeros((5, 5, 4), dtype=np.uint8)
    dark_background[:, :, 3] = 255
    dark_background[2, 2, :3] = 255
    light_mask, light_mode = foreground_mask(dark_background, mode="luminance-light", luminance_threshold=20)

    assert dark_mode == "luminance-dark"
    assert int(dark_mask.sum()) == 1
    assert dark_mask[2, 2]
    assert light_mode == "luminance-light"
    assert int(light_mask.sum()) == 1
    assert light_mask[2, 2]


def test_empty_mask_blocks_model_export_but_keeps_requested_previews(tmp_path):
    image_path = tmp_path / "empty.png"
    output_path = tmp_path / "exports" / "empty.obj"
    preview_dir = tmp_path / "previews"
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(image_path)

    with pytest.raises(ValueError, match="foreground mask is empty"):
        build_single_side_relief(image_path, output_path, ReliefParameters(), preview_dir=preview_dir)

    assert not output_path.exists()
    assert (preview_dir / "mask_preview.png").exists()
    assert (preview_dir / "heightmap_preview.png").exists()


def test_mesh_export_creates_parent_and_preserves_existing_target_on_validation_failure(tmp_path):
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    output_path = tmp_path / "nested" / "mesh.obj"

    export_obj(output_path, vertices, [[0, 1, 2]])
    assert output_path.exists()
    original = output_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="outside the vertex array"):
        export_obj(output_path, vertices, [[0, 1, 99]])

    assert output_path.read_text(encoding="utf-8") == original
    assert not [item for item in output_path.parent.iterdir() if item.name.endswith(".tmp")]


def test_project_loader_rejects_newer_file_version(tmp_path):
    project_path = tmp_path / "future.medalproj"
    project_path.write_text(json.dumps({"name": "Future", "file_version": 999}), encoding="utf-8")

    with pytest.raises(UnsupportedProjectVersionError, match="newer than supported"):
        load_project(project_path)


def test_project_asset_resolution_requires_project_asset_root(tmp_path):
    project_path = tmp_path / "safe.medalproj"
    save_project(create_project("Safe"), project_path)
    outside = tmp_path / "outside.png"
    Image.new("RGBA", (2, 2), (255, 255, 255, 255)).save(outside)

    with pytest.raises(ValueError, match="escapes the project asset directory"):
        resolve_project_asset(project_path, outside)


def test_failed_non_finite_project_save_does_not_replace_valid_file(tmp_path):
    project_path = tmp_path / "atomic.medalproj"
    project = create_project("Atomic")
    save_project(project, project_path)
    valid_text = project_path.read_text(encoding="utf-8")
    project.dimensions.width_mm = float("nan")

    with pytest.raises(ValueError):
        save_project(project, project_path)

    assert project_path.read_text(encoding="utf-8") == valid_text


def test_persisted_side_processing_settings_reach_runtime_parameters():
    project = create_project("Settings")
    project.front_relief.invert_height = True
    project.front_relief.mask_mode = "luminance-dark"
    project.front_relief.alpha_threshold = 7
    project.front_relief.luminance_threshold = 33.0
    project.front_relief.minimum_thickness_mm = 1.2
    project.front_relief.crop_to_foreground = False
    project.front_relief.crop_padding_px = 4

    params, quality = map_project_relief_parameters(project, "front", quality_mode="preview")

    assert quality == "preview"
    assert params.invert_height is True
    assert params.mask_mode == "luminance-dark"
    assert params.alpha_threshold == 7
    assert params.luminance_threshold == 33.0
    assert params.minimum_thickness_mm == 1.2
    assert params.crop_to_foreground is False
    assert params.crop_padding_px == 4


def test_manufacturing_gate_never_claims_unattended_safety():
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    faces = np.asarray([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int64)

    closed_report = basic_report(vertices, faces)
    open_report = basic_report(vertices[:3], [[0, 1, 2]])

    assert closed_report["manufacturing_gate"]["status"] == "review_required"
    assert closed_report["manufacturing_gate"]["topology_checks_passed"] is True
    assert closed_report["manufacturing_gate"]["unattended_manufacturing_recommended"] is False
    assert open_report["manufacturing_gate"]["status"] == "blocked"
    assert "open boundary edges are present" in open_report["manufacturing_gate"]["blockers"]
