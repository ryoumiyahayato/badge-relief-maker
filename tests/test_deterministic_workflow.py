import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from badge_relief_maker.app.core.approved_heightmap_builder import build_relief_from_approved_heightmap
from badge_relief_maker.app.core.deterministic_workflow import (
    draft_height_master,
    draft_solid_mask,
    export_workflow_artifacts,
    load_source_image,
    load_workflow_project,
    percentile_normalize,
)
from badge_relief_maker.app.core.relief_parameters import ReliefParameters


def test_sample_a_white_background_black_logo_keeps_only_logo():
    image = np.full((64, 64, 3), 255, dtype=np.uint8)
    image[18:46, 22:42] = 0

    solid = draft_solid_mask(image, mode="auto_background", explicit_background="bright", explicit_threshold=0.9)
    height = draft_height_master(image, solid.mask, mode="fixed", fixed_height=0.75)

    assert not solid.mask[0, 0]
    assert solid.mask[30, 30]
    assert solid.report["height_information_used"] is False
    assert np.all(height.height_master[solid.mask] == np.float32(0.75))
    assert np.all(height.height_master[~solid.mask] == 0.0)


def test_sample_b_whole_plate_black_lines_use_fixed_millimetre_engraving():
    image = np.full((48, 72), 255, dtype=np.uint8)
    image[20:24, 10:62] = 0
    solid = draft_solid_mask(image, mode="whole_plate")

    result = draft_height_master(
        image,
        solid.mask,
        mode="line_engrave",
        relief_height_mm=2.0,
        line_depth_mm=0.2,
        line_threshold=0.35,
        line_softness_px=0.0,
    )

    assert np.isclose(result.height_master[5, 5], 1.0)
    assert np.isclose(result.height_master[21, 30], 0.9)
    assert result.report["line_relief"]["applied_depth_mm"] == 0.2
    assert result.report["line_relief"]["clipped_pixel_count"] == 0


def test_sample_c_16bit_gradient_preserves_precision_and_inversion():
    gradient = np.linspace(0, 65535, 1024, dtype=np.uint16).reshape(32, 32)
    source = load_source_image(Image.fromarray(gradient))
    mask = np.ones(gradient.shape, dtype=bool)
    normal = draft_height_master(source, mask, mode="bright_high", low_percentile=0, high_percentile=100)
    inverted = draft_height_master(source, mask, mode="dark_high", low_percentile=0, high_percentile=100)

    assert np.unique(source.luminance).size > 256
    assert np.allclose(inverted.height_master, 1.0 - normal.height_master, atol=2e-6)
    assert normal.height_master.min() == 0.0
    assert normal.height_master.max() == 1.0


def test_sample_d_alpha_controls_solid_mask_and_ignores_transparent_rgb():
    rgba = np.zeros((40, 40, 4), dtype=np.uint8)
    rgba[:, :, :3] = [255, 0, 255]
    rgba[10:30, 12:28, :3] = [10, 20, 30]
    rgba[10:30, 12:28, 3] = 255

    result = draft_solid_mask(rgba, mode="auto_background")

    assert result.report["selected_method"] == "alpha"
    assert result.mask[20, 20]
    assert not result.mask[0, 0]
    assert int(result.mask.sum()) == 20 * 16


def test_sample_e_border_connected_background_preserves_enclosed_same_colour_hole():
    image = np.full((50, 50, 3), 255, dtype=np.uint8)
    image[10:40, 10] = 0
    image[10:40, 39] = 0
    image[10, 10:40] = 0
    image[39, 10:40] = 0

    result = draft_solid_mask(image, mode="auto_background", explicit_background="bright", explicit_threshold=0.9)

    assert not result.mask[0, 0]
    assert result.mask[10, 25]
    assert result.mask[25, 25]


def test_percentile_normalization_uses_only_solid_finite_pixels():
    values = np.asarray([[0.0, 999.0], [0.25, 0.75]], dtype=np.float64)
    mask = np.asarray([[False, False], [True, True]])

    normalized, report = percentile_normalize(values, mask, low_percentile=0, high_percentile=100)

    assert normalized[0, 1] == 0.0
    assert normalized[1, 0] == 0.0
    assert normalized[1, 1] == 1.0
    assert report["sample_count"] == 2


def test_uniform_solid_region_has_deterministic_midpoint_fallback():
    values = np.full((4, 5), 0.4, dtype=np.float32)
    mask = np.ones(values.shape, dtype=bool)

    normalized, report = percentile_normalize(values, mask)

    assert report["uniform_fallback"] is True
    assert np.all(normalized == np.float32(0.5))


def test_sample_f_real_photo_notice_and_manual_edit_roundtrip(tmp_path):
    yy, xx = np.mgrid[:32, :48]
    photo = np.dstack((xx / 47.0, yy / 31.0, (xx + yy) / 78.0))
    source = load_source_image(photo.astype(np.float32))
    solid = draft_solid_mask(source, mode="whole_plate")
    edits = [
        {
            "marker_type": "height",
            "stage": "local",
            "shape": "circle",
            "x": 0.5,
            "y": 0.5,
            "radius_normalized": 0.2,
            "operation": "set",
            "value": 0.8,
        }
    ]
    height = draft_height_master(source, solid.mask, mode="bright_high", height_edits=edits)
    artifacts = export_workflow_artifacts(
        source,
        solid.mask,
        height.height_master,
        tmp_path,
        solid_mask_confirmed=True,
        height_master_confirmed=True,
        solid_report=solid.report,
        height_report=height.report,
        source_parameters={"source_type": "real_photo"},
        height_edits=edits,
    )

    project = load_workflow_project(artifacts.paths["project"])
    report = json.loads(Path(artifacts.paths["build_report"]).read_text(encoding="utf-8"))
    reloaded_mask = np.asarray(Image.open(artifacts.paths["solid_mask"]).convert("L")) >= 128
    reloaded_height = np.asarray(Image.open(artifacts.paths["height_master_16bit"]), dtype=np.uint16) / 65535.0

    assert project["solid_mask_confirmed"] is True
    assert project["height_master_confirmed"] is True
    assert project["height_edits"] == edits
    assert report["luminance_is_depth"] is False
    assert "not recovered real geometry" in report["real_photo_notice"]
    assert np.array_equal(reloaded_mask, solid.mask)
    assert np.allclose(reloaded_height, height.height_master, atol=1.0 / 65535.0)


def test_sample_f_real_metal_photo_is_only_a_review_required_luminance_draft(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "real_metal_badge_photo.jpg"
    if not fixture.is_file():
        pytest.skip("real metal badge fixture is supplied by the remote fixture commit")

    source = load_source_image(fixture)
    solid = draft_solid_mask(source, mode="whole_plate")
    height = draft_height_master(source, solid.mask, mode="bright_high")
    artifacts = export_workflow_artifacts(
        source,
        solid.mask,
        height.height_master,
        tmp_path,
        solid_mask_confirmed=True,
        height_master_confirmed=False,
        solid_report=solid.report,
        height_report=height.report,
        source_parameters={"source_type": "real_photo"},
    )

    report = json.loads(Path(artifacts.paths["build_report"]).read_text(encoding="utf-8"))
    assert source.luminance.std() > 0.01
    assert report["status"] == "review_required"
    assert report["luminance_is_depth"] is False
    assert "not recovered real geometry" in report["real_photo_notice"]
    assert np.all(height.height_master[~solid.mask] == 0.0)


def test_unconfirmed_artifacts_are_marked_review_required(tmp_path):
    image = np.arange(64, dtype=np.uint8).reshape(8, 8)
    mask = np.ones((8, 8), dtype=bool)
    height = draft_height_master(image, mask, mode="bright_high")

    artifacts = export_workflow_artifacts(
        image,
        mask,
        height.height_master,
        tmp_path,
        solid_mask_confirmed=True,
        height_master_confirmed=False,
    )

    assert artifacts.report["status"] == "review_required"
    assert artifacts.project["review_required"] is True


def test_sample_h_approved_artifacts_build_closed_deterministic_mesh(tmp_path):
    rows, cols = 50, 70
    yy, xx = np.mgrid[:rows, :cols]
    mask = ((xx - 35) / 27.0) ** 2 + ((yy - 25) / 18.0) ** 2 <= 1.0
    mask[20:30, 30:40] = False
    height = np.zeros((rows, cols), dtype=np.float32)
    height[mask] = (xx[mask] / (cols - 1)).astype(np.float32)
    height_path = tmp_path / "height_master_16bit.png"
    mask_path = tmp_path / "solid_mask.png"
    Image.fromarray(np.round(height * 65535).astype(np.uint16)).save(height_path)
    Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(mask_path)
    params = ReliefParameters(width_mm=70, height_mm=50, base_thickness_mm=2, relief_height_mm=3, max_grid_cells=10000)

    first = build_relief_from_approved_heightmap(height_path, tmp_path / "first.stl", mask_path=mask_path, parameters=params)
    second = build_relief_from_approved_heightmap(height_path, tmp_path / "second.stl", mask_path=mask_path, parameters=params)

    assert first.report["topology"]["boundary_edge_count"] == 0
    assert first.report["topology"]["non_manifold_edge_count"] == 0
    assert first.report["topology"]["inconsistent_winding_edge_count"] == 0
    assert first.report["face_geometry"]["zero_area_face_count"] == 0
    assert first.report["components"]["inward_closed_component_count"] == 0
    assert first.report["deterministic_mesh_sha256"] == second.report["deterministic_mesh_sha256"]
    assert first.report["dimensions"]["actual_width_mm"] == 70.0
    assert first.report["dimensions"]["actual_height_mm"] == 50.0


def test_saved_project_reopens_with_identical_approved_truth_and_mesh_summary(tmp_path):
    from badge_relief_maker.app.core.deterministic_workflow import load_workflow_artifacts

    image = np.tile(np.linspace(0, 65535, 60, dtype=np.uint16), (40, 1))
    source = load_source_image(Image.fromarray(image))
    solid = draft_solid_mask(source, mode="whole_plate")
    height = draft_height_master(source, solid.mask, mode="bright_high", low_percentile=0, high_percentile=100)
    artifacts = export_workflow_artifacts(
        source,
        solid.mask,
        height.height_master,
        tmp_path,
        solid_mask_confirmed=True,
        height_master_confirmed=True,
        solid_report=solid.report,
        height_report=height.report,
    )
    loaded = load_workflow_artifacts(artifacts.paths["project"])
    params = ReliefParameters(width_mm=60, height_mm=40, base_thickness_mm=2, relief_height_mm=3, max_grid_cells=5000)
    first = build_relief_from_approved_heightmap(
        artifacts.paths["height_master_16bit"],
        tmp_path / "before.obj",
        mask_path=artifacts.paths["solid_mask"],
        parameters=params,
    )
    reloaded_height_path = tmp_path / "reopened_height.png"
    reloaded_mask_path = tmp_path / "reopened_mask.png"
    Image.fromarray(np.round(loaded.height_master * 65535).astype(np.uint16)).save(reloaded_height_path)
    Image.fromarray(loaded.solid_mask.astype(np.uint8) * 255).save(reloaded_mask_path)
    second = build_relief_from_approved_heightmap(
        reloaded_height_path,
        tmp_path / "after.obj",
        mask_path=reloaded_mask_path,
        parameters=params,
    )

    assert np.array_equal(loaded.solid_mask, solid.mask)
    assert np.allclose(loaded.height_master, height.height_master, atol=1.0 / 65535.0)
    assert first.report["deterministic_mesh_sha256"] == second.report["deterministic_mesh_sha256"]


def test_saved_project_detects_tampered_approved_mask(tmp_path):
    from badge_relief_maker.app.core.deterministic_workflow import load_workflow_artifacts

    image = np.arange(100, dtype=np.uint8).reshape(10, 10)
    mask = np.ones((10, 10), dtype=bool)
    height = draft_height_master(image, mask, mode="bright_high")
    artifacts = export_workflow_artifacts(
        image,
        mask,
        height.height_master,
        tmp_path,
        solid_mask_confirmed=True,
        height_master_confirmed=True,
    )
    Image.fromarray(np.zeros((10, 10), dtype=np.uint8)).save(artifacts.paths["solid_mask"])

    import pytest

    with pytest.raises(ValueError, match="hash mismatch"):
        load_workflow_artifacts(artifacts.paths["project"])
