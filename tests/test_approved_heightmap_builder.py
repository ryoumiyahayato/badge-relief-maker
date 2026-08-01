import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from badge_relief_maker.app.core.approved_heightmap_builder import build_relief_from_approved_heightmap
from badge_relief_maker.app.core.relief_parameters import ReliefParameters


def _approved_inputs(tmp_path, shape=(64, 48)):
    rows, cols = shape
    yy, xx = np.mgrid[:rows, :cols]
    mask = ((xx - cols / 2) / (cols * 0.38)) ** 2 + ((yy - rows / 2) / (rows * 0.42)) ** 2 <= 1.0
    height = np.zeros(shape, dtype=np.float32)
    height[mask] = 0.25 + 0.65 * (
        1.0
        - np.sqrt(
            np.clip(
                ((xx[mask] - cols / 2) / (cols * 0.38)) ** 2
                + ((yy[mask] - rows / 2) / (rows * 0.42)) ** 2,
                0.0,
                1.0,
            )
        )
    )
    height_path = tmp_path / "height_master_16bit.png"
    mask_path = tmp_path / "solid_mask.png"
    Image.fromarray(np.round(height * 65535.0).astype(np.uint16)).save(height_path)
    Image.fromarray((mask * 255).astype(np.uint8), mode="L").save(mask_path)
    return height_path, mask_path


def test_approved_16bit_heightmap_builds_closed_editable_obj_and_report(tmp_path):
    height_path, mask_path = _approved_inputs(tmp_path)
    output_path = tmp_path / "approved.obj"
    result = build_relief_from_approved_heightmap(
        height_path,
        output_path,
        mask_path=mask_path,
        min_feature_mm=0.3,
        parameters=ReliefParameters(
            width_mm=60.0,
            height_mm=80.0,
            base_thickness_mm=2.0,
            relief_height_mm=4.0,
            max_grid_cells=10000,
        ),
    )

    assert Path(result.output_path).is_file()
    assert (tmp_path / "build_report.json").is_file()
    saved_report = json.loads((tmp_path / "build_report.json").read_text(encoding="utf-8"))
    assert result.report["source_of_truth"] == ["approved solid_mask", "approved height_master"]
    assert result.report["automatic_height_synthesis"] is False
    assert result.report["source_image_used_for_mesh"] is False
    assert result.report["bbox"]["size_z"] > 5.0
    assert result.report["topology"]["boundary_edge_count"] == 0
    assert result.report["topology"]["non_manifold_edge_count"] == 0
    assert result.report["editable_master"] is False
    assert result.report["export_format"] == "obj"
    assert result.report["sampling"]["final_grid_spacing_mm"]["x"] > 0
    assert result.report["sampling"]["three_sample_recommended_spacing_mm"] == pytest.approx(0.1)
    assert len(result.report["input_hashes"]["approved_height_master_sha256"]) == 64
    assert saved_report["deterministic_mesh_sha256"] == result.report["deterministic_mesh_sha256"]


def test_mask_is_required_and_never_inferred_from_height(tmp_path):
    height_path, _ = _approved_inputs(tmp_path)
    with pytest.raises((FileNotFoundError, ValueError), match="solid mask"):
        build_relief_from_approved_heightmap(height_path, tmp_path / "bad.stl")


def test_misaligned_approved_mask_is_rejected_not_resized(tmp_path):
    height_path, _ = _approved_inputs(tmp_path)
    bad_mask = tmp_path / "bad_mask.png"
    Image.fromarray(np.ones((20, 20), dtype=np.uint8) * 255, mode="L").save(bad_mask)
    with pytest.raises(ValueError, match="does not match"):
        build_relief_from_approved_heightmap(height_path, tmp_path / "bad.stl", mask_path=bad_mask)


def test_8bit_preview_is_rejected_as_formal_height_master(tmp_path):
    height = np.arange(64, dtype=np.uint8).reshape(8, 8)
    mask = np.ones((8, 8), dtype=np.uint8) * 255
    height_path = tmp_path / "height_master_preview.png"
    mask_path = tmp_path / "solid_mask.png"
    Image.fromarray(height, mode="L").save(height_path)
    Image.fromarray(mask, mode="L").save(mask_path)
    with pytest.raises(ValueError, match="8-bit images are display previews"):
        build_relief_from_approved_heightmap(height_path, tmp_path / "bad.stl", mask_path=mask_path)
