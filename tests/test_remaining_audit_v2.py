import json
import os
import subprocess

import numpy as np
import pytest
from PIL import Image

from badge_relief_maker import __version__
from badge_relief_maker.app.main import main
from badge_relief_maker.app.core.double_side_builder import align_relief_fields, build_fused_double_sided_relief
from badge_relief_maker.app.core.mesh_analysis import overhang_tool_access_report, self_intersection_report
from badge_relief_maker.app.core.project_parameters import relief_parameters_from_project, validate_project_parameters
from badge_relief_maker.app.core.project_io import (
    ProjectFormatError,
    asset_root_for,
    create_project,
    import_image_asset,
    load_project,
    resolve_project_asset,
    save_project,
)
from badge_relief_maker.app.core.project_model import ImageRecord, MedalProject
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief


def test_cli_reports_the_packaged_product_version(capsys):
    with pytest.raises(SystemExit, match="0"):
        main(["--version"])

    assert capsys.readouterr().out.strip() == f"Badge Relief Maker {__version__}"


def test_single_side_does_not_validate_unused_fused_total_thickness():
    project = create_project("Independent thickness")
    project.dimensions.total_thickness_mm = "unused by a single side"

    assert validate_project_parameters(project, side_name="front") == (80.0, 80.0)
    with pytest.raises(ValueError, match="total_thickness_mm must be numeric"):
        validate_project_parameters(project, fused=True)


@pytest.mark.parametrize("unsafe_number", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_project_load_rejects_non_finite_json_numbers(tmp_path, unsafe_number):
    project_path = tmp_path / "unsafe.medalproj"
    project_path.write_text(
        '{"name":"Unsafe","dimensions":{"width_mm":' + unsafe_number + "}}",
        encoding="utf-8",
    )

    with pytest.raises(ProjectFormatError, match="non-finite"):
        load_project(project_path)


def test_project_model_filters_malformed_v2_visual_edit_records():
    project = MedalProject.from_dict(
        {
            "name": "Malformed visual records",
            "front_relief": {
                "manual_crop_box": [0, "bad", 10, 10],
                "perspective_quad": [[0, 0], [1, 0], [1, 2], [0, 1]],
                "mask_edits": [{"operation": "remove"}, "bad"],
                "region_layers": [42, {"height_normalized": 0.5}],
            },
        }
    )

    assert project.front_relief.manual_crop_box is None
    assert project.front_relief.perspective_quad is None
    assert project.front_relief.mask_edits == [{"operation": "remove"}]
    assert project.front_relief.region_layers == [{"height_normalized": 0.5}]


def test_v1_load_v2_save_preserves_equivalent_single_side_build(tmp_path):
    source = tmp_path / "source.png"
    pixels = np.zeros((10, 12, 4), dtype=np.uint8)
    pixels[2:9, 3:10, :3] = 160
    pixels[2:9, 3:10, 3] = 255
    Image.fromarray(pixels, mode="RGBA").save(source)
    project_path = tmp_path / "migration.medalproj"
    project = create_project("Migration equivalence")
    project.front_relief.mask_mode = "alpha"
    project.front_relief.quality_mode = "preview"
    save_project(project, project_path)
    import_image_asset(project, project_path, source, "front")
    save_project(project, project_path)

    raw = json.loads(project_path.read_text(encoding="utf-8"))
    raw["file_version"] = 1
    for key in (
        "uniform_height_normalized",
        "smooth_strength",
        "detail_sharpness",
        "process_profile",
        "manual_crop_box",
        "perspective_quad",
        "mask_edits",
        "region_layers",
    ):
        raw["front_relief"].pop(key, None)
    raw.pop("double_side", None)
    project_path.write_text(json.dumps(raw), encoding="utf-8")

    migrated = load_project(project_path)
    imported = resolve_project_asset(project_path, migrated.front_image.path)
    before_params, _ = relief_parameters_from_project(migrated, "front", "preview")
    before = build_single_side_relief(imported, parameters=before_params)
    save_project(migrated, project_path)
    reopened = load_project(project_path)
    after_params, _ = relief_parameters_from_project(reopened, "front", "preview")
    after = build_single_side_relief(imported, parameters=after_params)

    assert np.array_equal(before.faces, after.faces)
    assert np.allclose(before.vertices, after.vertices)
    assert before.report["bbox"] == after.report["bbox"]


def test_asset_resolution_rejects_symlink_or_junction_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    Image.new("RGBA", (2, 2), (255, 255, 255, 255)).save(outside / "escaped.png")
    project_path = tmp_path / "links.medalproj"
    save_project(create_project("Links"), project_path)
    images = asset_root_for(project_path) / "images"
    link = images / "external-link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"filesystem does not permit a test reparse point: {exc}")
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.skip(f"filesystem does not permit a test junction: {completed.stderr or completed.stdout}")

    stored = link.relative_to(project_path.parent) / "escaped.png"
    with pytest.raises(ValueError, match="escapes"):
        resolve_project_asset(project_path, stored)


def _exact_alignment_inputs():
    shape = (7, 9)
    front_mask = np.zeros(shape, dtype=bool)
    back_mask = np.zeros(shape, dtype=bool)
    back_mask[3, 1] = True
    return front_mask, np.zeros(shape), back_mask, back_mask.astype(float)


def test_double_alignment_flip_and_signed_offsets_use_physical_grid():
    front_mask, front_height, back_mask, back_height = _exact_alignment_inputs()
    _, _, flipped, _ = align_relief_fields(
        front_mask,
        front_height,
        back_mask,
        back_height,
        90.0,
        70.0,
        63,
        flip_back_horizontal=True,
    )
    _, _, shifted, _ = align_relief_fields(
        front_mask,
        front_height,
        back_mask,
        back_height,
        90.0,
        70.0,
        63,
        back_offset_x_mm=10.0,
        back_offset_y_mm=-10.0,
        flip_back_horizontal=False,
    )
    _, _, opposite_shift, _ = align_relief_fields(
        front_mask,
        front_height,
        back_mask,
        back_height,
        90.0,
        70.0,
        63,
        back_offset_x_mm=-10.0,
        back_offset_y_mm=10.0,
        flip_back_horizontal=False,
    )

    assert np.argwhere(flipped > 0).tolist() == [[3, 7]]
    assert np.argwhere(shifted > 0).tolist() == [[2, 2]]
    assert np.argwhere(opposite_shift > 0).tolist() == [[4, 0]]


def test_double_alignment_rotation_and_scale_transform_asymmetric_back():
    front_mask, front_height, back_mask, back_height = _exact_alignment_inputs()
    _, _, rotated, _ = align_relief_fields(
        front_mask,
        front_height,
        back_mask,
        back_height,
        90.0,
        70.0,
        63,
        back_rotation_deg=180.0,
        flip_back_horizontal=False,
    )
    centered_mask = np.zeros(back_mask.shape, dtype=bool)
    centered_mask[3, 4] = True
    scaled_mask, _, scaled, _ = align_relief_fields(
        front_mask,
        front_height,
        centered_mask,
        centered_mask.astype(float),
        90.0,
        70.0,
        63,
        back_scale=2.0,
        flip_back_horizontal=False,
    )

    assert np.argwhere(rotated > 0).tolist() == [[3, 7]]
    assert int(np.count_nonzero(scaled_mask)) > 1
    assert int(np.count_nonzero(scaled)) > 1


def test_double_alignment_footprint_modes_are_exact():
    front = np.zeros((7, 9), dtype=bool)
    back = np.zeros((7, 9), dtype=bool)
    front[2:5, 1:5] = True
    back[2:5, 3:7] = True
    heights = np.ones((7, 9), dtype=float)
    expected = {
        "union": front | back,
        "intersection": front & back,
        "front": front,
        "back": back,
    }
    for mode, expected_mask in expected.items():
        footprint, _, _, report = align_relief_fields(
            front,
            heights,
            back,
            heights,
            90.0,
            70.0,
            63,
            flip_back_horizontal=False,
            footprint_mode=mode,
        )
        assert np.array_equal(footprint, expected_mask)
        assert report["footprint_mode"] == mode


def test_fused_double_z_size_is_body_plus_both_outward_reliefs():
    mask = np.ones((5, 7), dtype=bool)
    vertices, _, _, _, _, _ = build_fused_double_sided_relief(
        mask,
        np.ones(mask.shape),
        mask,
        np.ones(mask.shape),
        70.0,
        50.0,
        4.0,
        2.0,
        1.5,
        35,
        alignment={"flip_back_horizontal": False},
    )

    assert np.ptp(vertices[:, 2]) == pytest.approx(7.5)


def test_self_intersection_candidate_limit_is_reported_deterministically():
    triangle = np.asarray([[-1.0, -1.0, 0.0], [1.0, -1.0, 0.0], [0.0, 1.0, 0.0]])
    vertices = np.vstack([triangle for _ in range(4)])
    faces = np.arange(12, dtype=np.int64).reshape((4, 3))

    report = self_intersection_report(vertices, faces, max_candidate_pairs=1)

    assert report["complete"] is False
    assert report["limit_reached"] is True
    assert report["candidate_limit"] == 1
    assert report["candidate_pair_count"] == 1
    assert report["tested_pair_count"] == 1
    assert report["intersection_pair_count"] == 1


def test_self_intersection_avoids_separated_coplanar_false_positive():
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [2.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
            [2.0, 1.0, 0.0],
        ]
    )
    report = self_intersection_report(vertices, np.asarray([[0, 1, 2], [3, 4, 5]]))

    assert report["complete"] is True
    assert report["intersection_pair_count"] == 0


def test_process_reports_state_direction_and_process_specific_limitations():
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]],
        dtype=float,
    )
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)

    cnc = overhang_tool_access_report(vertices, faces, "cnc")
    mould = overhang_tool_access_report(vertices, faces, "mould")

    assert cnc["review_required"] is True
    assert "toolpaths" in cnc["note"]
    assert "parting line" in mould["note"]
    assert cnc["direction_assumption"].startswith("+Z")


def test_gui_freezes_previews_and_rejects_source_space_height_edits():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from badge_relief_maker.app.ui.editor_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = create_project("GUI guard")
    window.project.front_image = ImageRecord(role="front", path="unused.png")
    window.edit_tool_combo.setCurrentText("height set")

    window._preview_clicked("source", 0.5, 0.5)
    assert window.project.manual_markers == []
    window._set_building(True)
    assert not window.source_preview.isEnabled()
    assert not window.mask_preview.isEnabled()
    assert not window.height_preview.isEnabled()
    assert not window.side_combo.isEnabled()
    window._set_building(False)
    assert window.source_preview.isEnabled()
    window.close()
    app.processEvents()
