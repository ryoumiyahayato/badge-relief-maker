import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

from badge_relief_maker.app.core.contour_extractor import connected_regions, region_report
from badge_relief_maker.app.core.double_side_builder import build_fused_double_sided_relief
from badge_relief_maker.app.core.export_validation import validate_export
from badge_relief_maker.app.core.height_markers import apply_manual_height_markers
from badge_relief_maker.app.core.height_processing import apply_region_layers
from badge_relief_maker.app.core.manufacturability_check import basic_report
from badge_relief_maker.app.core.masked_solid_builder import build_layered_relief_solid, build_masked_relief_solid
from badge_relief_maker.app.core.mesh_analysis import footprint_feature_report, self_intersection_report
from badge_relief_maker.app.core.mesh_exporter import export_mesh
from badge_relief_maker.app.core.mesh_repair import orient_closed_components_outward, repair_mesh_basic
from badge_relief_maker.app.core.project_build import build_fused_double_side_from_project_file
from badge_relief_maker.app.core.project_io import create_project, import_image_asset, load_project, save_project
from badge_relief_maker.app.core.project_model import PROJECT_FILE_VERSION
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import prepare_relief_field


def _topology(vertices, faces):
    vertices, faces, _ = repair_mesh_basic(vertices, faces)
    return basic_report(
        vertices,
        faces,
        analysis_context={
            "mask": np.ones((2, 2), dtype=bool),
            "heightmap": np.ones((2, 2), dtype=float),
            "width_mm": 10.0,
            "height_mm": 10.0,
            "base_thickness_mm": 2.0,
            "relief_height_mm": 1.0,
            "construction": "indexed_heightfield",
            "edge_style": "straight",
        },
    )


def test_version_one_project_is_migrated_to_v2(tmp_path):
    project_path = tmp_path / "legacy.medalproj"
    project_path.write_text(json.dumps({"name": "Legacy", "file_version": 1}), encoding="utf-8")
    project = load_project(project_path)
    assert project.file_version == PROJECT_FILE_VERSION == 2
    assert project.front_relief.mask_edits == []
    assert project.double_side.back_scale == 1.0
    save_project(project, project_path)
    assert json.loads(project_path.read_text(encoding="utf-8"))["file_version"] == 2


def test_prepare_field_applies_manual_crop_mask_edit_and_perspective(tmp_path):
    path = tmp_path / "source.png"
    data = np.zeros((20, 30, 4), dtype=np.uint8)
    data[..., 3] = 255
    Image.fromarray(data, mode="RGBA").save(path)
    params = ReliefParameters(
        mask_mode="alpha",
        manual_crop_box=(5, 3, 25, 18),
        perspective_quad=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        manual_mask_edits=(
            {"operation": "remove", "x": 0.5, "y": 0.5, "radius_normalized": 0.1},
        ),
    )
    prepared = prepare_relief_field(path, params)
    assert prepared.report["manual_crop_box"] == (5, 3, 25, 18)
    assert prepared.report["mask_edits"]["applied_edit_count"] == 1
    assert prepared.report["image_source"]["perspective"]["output_size"] == [29, 19]
    assert not prepared.mask.all()


def test_region_layer_lock_prevents_later_height_edit():
    mask = np.ones((7, 7), dtype=bool)
    base = np.zeros((7, 7), dtype=float)
    layer = {"x": 0.5, "y": 0.5, "radius_px": 2, "height_normalized": 0.8, "locked": True}
    layered, locked, report = apply_region_layers(base, mask, [layer])
    edited, _ = apply_manual_height_markers(
        layered,
        mask & ~locked,
        {"x": 0.5, "y": 0.5, "radius_px": 3, "height_normalized": 0.1},
    )
    assert report["locked_pixel_count"] > 0
    assert np.isclose(float(edited[3, 3]), 0.8)


def test_height_smooth_marker_changes_a_peak():
    mask = np.ones((5, 5), dtype=bool)
    height = np.zeros((5, 5), dtype=float)
    height[2, 2] = 1.0
    smoothed, report = apply_manual_height_markers(
        height,
        mask,
        {"operation": "smooth", "strength": 1.0, "x": 0.5, "y": 0.5, "radius_px": 1},
    )
    assert report["applied_marker_count"] == 1
    assert 0.0 < float(smoothed[2, 2]) < 1.0


def test_bevel_and_rounded_edges_remain_closed_and_keep_dimensions():
    mask = np.ones((4, 4), dtype=bool)
    height = np.linspace(0.2, 1.0, 16).reshape((4, 4))
    for style, bevel, radius in (("bevel", 0.8, 0.0), ("rounded", 0.0, 0.8), ("sloped", 0.6, 0.0)):
        vertices, faces = build_masked_relief_solid(
            height,
            mask,
            20.0,
            10.0,
            2.0,
            3.0,
            edge_style=style,
            bevel_mm=bevel,
            radius_mm=radius,
        )
        vertices, faces, _ = repair_mesh_basic(vertices, faces)
        report = basic_report(vertices, faces)
        assert report["topology"]["closed_oriented_manifold"] is True
        assert report["components"]["inward_closed_component_count"] == 0
        assert abs(report["bbox"]["size_x"] - 20.0) < 1e-9
        assert abs(report["bbox"]["size_y"] - 10.0) < 1e-9


def test_exact_layered_builder_preserves_sharp_steps_without_open_edges():
    mask = np.ones((2, 2), dtype=bool)
    height = np.asarray([[0.25, 1.0], [0.5, 0.75]], dtype=float)
    vertices, faces = build_layered_relief_solid(height, mask, 20.0, 20.0, 2.0, 4.0)
    vertices, faces, _ = repair_mesh_basic(vertices, faces)
    report = basic_report(vertices, faces)
    assert report["topology"]["closed_oriented_manifold"] is True
    assert report["topology"]["boundary_edge_count"] == 0
    assert set(np.round(vertices[:, 2], 6)) == {-2.0, 1.0, 2.0, 3.0, 4.0}


def test_orientation_repair_reverses_an_inward_component():
    vertices, faces = build_masked_relief_solid(np.ones((2, 2)), np.ones((2, 2), dtype=bool), 10, 10, 2, 1)
    inward = faces[:, [0, 2, 1]]
    _, repaired, report = orient_closed_components_outward(vertices, inward)
    result = basic_report(vertices, repaired)
    assert report["reversed_inward_components"] == 1
    assert result["face_geometry"]["signed_volume_mm3"] > 0.0


def test_self_intersection_detects_crossing_triangles():
    vertices = np.asarray(
        [
            [-1, -1, 0],
            [1, -1, 0],
            [0, 1, 0],
            [0, -0.5, -1],
            [0, -0.5, 1],
            [0, 0.8, 0],
        ],
        dtype=float,
    )
    report = self_intersection_report(vertices, np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int64))
    assert report["complete"] is True
    assert report["intersection_pair_count"] == 1


def test_feature_report_flags_thin_and_tiny_components():
    mask = np.zeros((10, 10), dtype=bool)
    mask[1:9, 1:3] = True
    mask[9, 9] = True
    report = footprint_feature_report(mask, np.zeros(mask.shape), 10, 10, 0.2, 0.0, "fdm", 0.8)
    assert report["local_wall_thickness"]["violation"] is True
    assert report["floating_components"]["tiny_component_count"] == 0  # one 1 mm2 pixel is above the FDM area threshold
    assert report["floating_components"]["component_count"] == 2


def test_connected_region_extraction_is_deterministic():
    mask = np.zeros((5, 5), dtype=bool)
    mask[0:2, 0:2] = True
    mask[4, 4] = True
    regions = connected_regions(mask)
    assert [int(region.sum()) for region in regions] == [4, 1]
    assert region_report(mask)["region_count"] == 2


def test_fused_double_builder_produces_one_closed_component():
    mask = np.ones((5, 7), dtype=bool)
    front = np.linspace(0.0, 1.0, mask.size).reshape(mask.shape)
    back = np.flip(front, axis=1)
    vertices, faces, footprint, front_field, back_field, alignment = build_fused_double_sided_relief(
        mask,
        front,
        mask,
        back,
        70.0,
        50.0,
        4.0,
        2.0,
        1.5,
        400,
        alignment={"back_rotation_deg": 3.0, "back_offset_x_mm": 1.0},
    )
    result = basic_report(vertices, faces)
    assert footprint.shape == front_field.shape == back_field.shape
    assert alignment["footprint_component_count"] == 1
    assert result["components"]["component_count"] == 1
    assert result["topology"]["closed_oriented_manifold"] is True
    assert result["face_geometry"]["signed_volume_mm3"] > 0.0
    assert abs(result["bbox"]["size_x"] - 70.0) < 1e-9
    assert abs(result["bbox"]["size_y"] - 50.0) < 1e-9


def test_project_fused_double_export_roundtrip(tmp_path):
    front_path = tmp_path / "front.png"
    back_path = tmp_path / "back.png"
    Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(front_path)
    Image.new("RGBA", (8, 8), (180, 180, 180, 255)).save(back_path)
    project = create_project("Fused")
    project_path = tmp_path / "fused.medalproj"
    save_project(project, project_path)
    import_image_asset(project, project_path, front_path, "front")
    import_image_asset(project, project_path, back_path, "back")
    save_project(project, project_path)
    result = build_fused_double_side_from_project_file(project_path, export_format="obj", quality_mode="preview")
    loaded = load_project(project_path)
    assert Path(result.output_path).is_file()
    assert result.report["assembly_mode"] == "aligned_fused_double_side"
    assert result.report["components"]["component_count"] == 1
    assert loaded.export_history[-1].notes.startswith("fused double-side")


def test_packaging_configuration_is_present():
    root = Path(__file__).parents[1]
    assert (root / "BadgeReliefMaker.spec").is_file()
    assert (root / "build_windows.ps1").is_file()
    assert (root / "packaging_entry.py").is_file()
    assert (root / "version_info.txt").is_file()
    assert 'version=str(root / "version_info.txt")' in (root / "BadgeReliefMaker.spec").read_text(encoding="utf-8")
    version_text = (root / "version_info.txt").read_text(encoding="utf-8")
    assert 'version = "0.3.0"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "FileVersion" in version_text
    assert "0.3.0" in version_text


def test_all_export_formats_roundtrip_through_independent_loader(tmp_path):
    vertices, faces = build_masked_relief_solid(np.ones((3, 3)), np.ones((3, 3), dtype=bool), 30.0, 20.0, 2.0, 3.0)
    expected = [30.0, 20.0, 5.0]
    for suffix in ("obj", "stl", "glb"):
        path = tmp_path / f"accepted.{suffix}"
        export_mesh(path, vertices, faces)
        report = validate_export(path, expected_size_mm=expected)
        assert report["geometry_count"] == 1
        assert report["watertight"] is True
        assert report["winding_consistent"] is True
        assert report["positive_volume"] is True
        assert report["dimensions_match"] is True


def test_gui_constructs_offscreen():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from badge_relief_maker.app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.source_preview is not None
    assert window.mask_preview is not None
    assert window.height_preview is not None
    assert window.report_box.isReadOnly()
    window.close()
    app.processEvents()
