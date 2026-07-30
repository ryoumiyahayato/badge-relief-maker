from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from badge_relief_maker.app.core.adaptive_mesh import (
    build_adaptive_double_sided_relief_solid,
    build_adaptive_layered_relief_solid,
    build_adaptive_relief_solid,
)
from badge_relief_maker.app.core.bezier_contours import (
    apply_bezier_contours,
    default_bezier_contour_from_mask,
)
from badge_relief_maker.app.core.confidence_preview import build_uncertainty_map
from badge_relief_maker.app.core.lineart_regions import analyze_lineart_regions
from badge_relief_maker.app.core.profile_inspection import sample_height_profile
from badge_relief_maker.app.core.project_io import create_project, load_project, save_project
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.semantic_annotations import SEMANTIC_HEIGHTS, apply_semantic_heights
from badge_relief_maker.app.core.semantic_annotations import apply_semantic_topology
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief, prepare_relief_field


def _final_brush(role, x, y, *, amount=0.12, locked=True, radius=3.0):
    return {
        "annotation_id": f"{role}-{x}-{y}",
        "tool": "brush",
        "role": role,
        "x": float(x),
        "y": float(y),
        "coordinate_space": "final",
        "radius": float(radius),
        "radius_is_normalized": False,
        "amount": float(amount),
        "locked": bool(locked),
    }


def _rectangle_contour(x0, y0, x1, y1, operation):
    anchors = ([x0, y0], [x1, y0], [x1, y1], [x0, y1])
    return {
        "operation": operation,
        "closed": True,
        "points": [
            {"anchor": list(anchor), "in": list(anchor), "out": list(anchor)}
            for anchor in anchors
        ],
    }


def _boundary_edge_count(faces):
    usage = Counter(
        tuple(sorted((int(first), int(second))))
        for face in np.asarray(faces)
        for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
    )
    return sum(count == 1 for count in usage.values())


def test_fixed_semantic_levels_and_relative_adjustments_are_distinct():
    mask = np.ones((40, 40), dtype=bool)
    source = np.full(mask.shape, 0.50, dtype=np.float32)
    annotations = [
        _final_brush("base", 5, 5),
        _final_brush("low", 13, 5),
        _final_brush("mid", 21, 5),
        _final_brush("high", 29, 5),
        _final_brush("top", 35, 5),
        _final_brush("raise", 12, 25, amount=0.15),
        _final_brush("recess", 28, 25, amount=0.20),
    ]

    result, affected, report = apply_semantic_heights(source, mask, annotations, locked=True)

    assert result[5, 5] == pytest.approx(SEMANTIC_HEIGHTS["base"])
    assert result[5, 13] == pytest.approx(SEMANTIC_HEIGHTS["low"])
    assert result[5, 21] == pytest.approx(SEMANTIC_HEIGHTS["mid"])
    assert result[5, 29] == pytest.approx(SEMANTIC_HEIGHTS["high"])
    assert result[5, 35] == pytest.approx(SEMANTIC_HEIGHTS["top"])
    assert result[25, 12] == pytest.approx(0.65)
    assert result[25, 28] == pytest.approx(0.30)
    assert affected.any()
    assert report["role_counts"] == {
        "base": 1,
        "low": 1,
        "mid": 1,
        "high": 1,
        "top": 1,
        "raise": 1,
        "recess": 1,
    }


def test_lock_confirmed_regions_controls_final_override_order(tmp_path):
    image_path = tmp_path / "locked.png"
    Image.new("RGBA", (40, 40), (100, 100, 100, 255)).save(image_path)
    semantic = (
        {
            "annotation_id": "locked-top",
            "tool": "brush",
            "role": "top",
            "x": 20.0,
            "y": 20.0,
            "coordinate_space": "pixel",
            "radius_px": 6.0,
            "locked": True,
        },
    )
    layer = (
        {
            "coordinate_space": "final_normalized",
            "x": 0.5,
            "y": 0.5,
            "radius_normalized": 0.10,
            "height_normalized": 0.20,
            "locked": True,
        },
    )
    common = dict(
        mask_mode="alpha",
        crop_to_foreground=False,
        min_component_pixels=1,
        semantic_annotations=semantic,
        region_layers=layer,
    )

    locked = prepare_relief_field(image_path, ReliefParameters(**common, lock_confirmed_regions=True))
    unlocked = prepare_relief_field(image_path, ReliefParameters(**common, lock_confirmed_regions=False))

    assert locked.heightmap[20, 20] == pytest.approx(SEMANTIC_HEIGHTS["top"])
    assert unlocked.heightmap[20, 20] == pytest.approx(0.20)
    assert locked.report["semantic_annotations"]["locked"]["applied_annotation_count"] == 1
    assert unlocked.report["semantic_annotations"]["locked_before_automatic_adjustments"]["applied_annotation_count"] == 1


def test_lineart_review_labels_dark_artwork_and_light_cells_separately():
    rgba = np.full((60, 80, 4), 255, dtype=np.uint8)
    rgba[18:42, 28:52, :3] = 20
    mask = np.ones((60, 80), dtype=bool)

    labels, report = analyze_lineart_regions(rgba, mask, minimum_pixels=10)

    assert labels[30, 40] > 0
    assert labels[5, 5] > 0
    assert labels[30, 40] != labels[5, 5]
    assert {item["tone_class"] for item in report["regions"]} == {"light", "dark"}


def test_part_semantics_can_fill_an_enclosed_void_without_selecting_outer_background():
    rgba = np.full((50, 50, 4), 255, dtype=np.uint8)
    mask = np.ones((50, 50), dtype=bool)
    mask[18:32, 18:32] = False
    labels, report = analyze_lineart_regions(rgba, mask, minimum_pixels=4)
    void_region = next(item for item in report["regions"] if item["occupancy_class"] == "enclosed_void")
    x, y = void_region["centroid_normalized"]
    annotation = {
        "tool": "part",
        "role": "base",
        "x": x,
        "y": y,
        "coordinate_space": "normalized",
        "radius_normalized": 0.03,
        "locked": True,
    }

    filled, topology_report = apply_semantic_topology(mask, [annotation], lineart_labels=labels)

    assert filled.all()
    assert topology_report["applied_topology_count"] == 1


def test_uncertainty_map_is_explicitly_not_a_probability():
    rgba = np.full((40, 40, 4), 255, dtype=np.uint8)
    rgba[15:25, 15:25, :3] = 30
    mask = np.ones((40, 40), dtype=bool)
    labels, regions = analyze_lineart_regions(rgba, mask, minimum_pixels=4)

    uncertainty, report = build_uncertainty_map(
        rgba,
        mask,
        lineart_labels=labels,
        lineart_report=regions,
    )

    assert uncertainty.shape == mask.shape
    assert np.all((uncertainty >= 0.0) & (uncertainty <= 1.0))
    assert report["unresolved_region_count"] == 2
    assert "not probabilities" in report["interpretation"]


def test_profile_uses_real_model_dimensions_and_millimeter_height():
    field = np.tile(np.linspace(0.0, 1.0, 5, dtype=np.float32), (3, 1))
    mask = np.ones(field.shape, dtype=bool)

    profile = sample_height_profile(
        field,
        mask,
        orientation="horizontal",
        position_normalized=0.5,
        width_mm=40.0,
        height_mm=20.0,
        relief_height_mm=3.0,
    )

    assert profile["physical_position_mm"] == pytest.approx(10.0)
    assert profile["coordinates_mm"].tolist() == pytest.approx([0.0, 10.0, 20.0, 30.0, 40.0])
    assert profile["heights_mm"].tolist() == pytest.approx([0.0, 0.75, 1.5, 2.25, 3.0])


def test_bezier_contours_apply_ordered_boolean_footprint_operations():
    mask = np.zeros((100, 100), dtype=bool)
    contours = [
        _rectangle_contour(0.10, 0.10, 0.90, 0.90, "replace"),
        _rectangle_contour(0.40, 0.40, 0.60, 0.60, "remove"),
    ]

    result, report = apply_bezier_contours(mask, contours)

    assert result[20, 20]
    assert not result[50, 50]
    assert not result[2, 2]
    assert report["applied_contour_count"] == 2
    assert report["changed_pixel_count"] > 0


def test_bezier_contour_can_be_initialized_from_a_mask():
    mask = np.zeros((80, 100), dtype=bool)
    mask[10:70, 20:80] = True

    contour = default_bezier_contour_from_mask(mask, maximum_anchors=12)
    result, report = apply_bezier_contours(np.zeros_like(mask), [contour])

    assert contour is not None
    assert 4 <= len(contour["points"]) <= 12
    assert report["applied_contour_count"] == 1
    assert result.sum() > mask.sum() * 0.70


def test_adaptive_continuous_mesh_is_closed_and_reduces_flat_interior_cells():
    mask = np.ones((64, 64), dtype=bool)
    field = np.full(mask.shape, 0.45, dtype=np.float32)

    vertices, faces, report = build_adaptive_relief_solid(
        field,
        mask,
        40.0,
        40.0,
        2.0,
        3.0,
        coarse_cell_px=8,
    )

    assert len(vertices) > 0 and len(faces) > 0
    assert _boundary_edge_count(faces) == 0
    assert report["coarse_leaf_count"] > 0
    assert report["leaf_reduction_ratio"] > 0.40
    assert report["feature_detection"]["contour_pixel_count"] > 0


def test_adaptive_layered_mesh_preserves_exact_steps_and_is_closed():
    mask = np.ones((32, 32), dtype=bool)
    field = np.where(np.indices(mask.shape)[1] < 16, 0.25, 0.75).astype(np.float32)

    vertices, faces, report = build_adaptive_layered_relief_solid(
        field,
        mask,
        40.0,
        40.0,
        2.0,
        4.0,
        coarse_cell_px=8,
    )

    assert _boundary_edge_count(faces) == 0
    assert report["exact_layers"] is True
    assert report["overused_interval_count"] == 0
    assert report["feature_detection"]["height_discontinuity_pixel_count"] > 0
    top_levels = {round(value, 6) for value in vertices[:, 2] if value >= 0.0}
    assert {1.0, 3.0}.issubset(top_levels)


def test_adaptive_fused_mesh_uses_front_and_back_features_on_one_closed_grid():
    mask = np.ones((64, 64), dtype=bool)
    front = np.full(mask.shape, 0.30, dtype=np.float32)
    front[24:40, 24:40] = 0.85
    back = np.full(mask.shape, 0.20, dtype=np.float32)
    back[8:12, :] = 0.70

    vertices, faces, report = build_adaptive_double_sided_relief_solid(
        front,
        back,
        mask,
        50.0,
        40.0,
        3.0,
        2.0,
        1.0,
        coarse_cell_px=8,
    )

    assert _boundary_edge_count(faces) == 0
    assert report["double_sided"] is True
    assert report["coarse_leaf_count"] > 0
    assert report["feature_detection"]["front"]["height_discontinuity_pixel_count"] > 0
    assert report["feature_detection"]["back"]["height_discontinuity_pixel_count"] > 0
    assert vertices[:, 2].max() == pytest.approx(1.5 + 0.85 * 2.0, abs=0.01)
    assert vertices[:, 2].min() == pytest.approx(-1.5 - 0.70, abs=0.01)


def test_new_project_fields_roundtrip_and_pipeline_emits_review_artifacts(tmp_path):
    project = create_project("Semantic persistence")
    project.front_relief.semantic_annotations = [
        {
            "annotation_id": "one",
            "tool": "brush",
            "role": "high",
            "x": 0.5,
            "y": 0.5,
            "coordinate_space": "normalized",
            "radius_normalized": 0.1,
            "locked": True,
        }
    ]
    project.front_relief.bezier_contours = [_rectangle_contour(0.1, 0.1, 0.9, 0.9, "replace")]
    project.front_relief.lock_confirmed_regions = False
    project.front_relief.adaptive_mesh_enabled = True
    project_path = tmp_path / "semantic.medalproj"

    save_project(project, project_path)
    loaded = load_project(project_path)

    assert loaded.front_relief.semantic_annotations == project.front_relief.semantic_annotations
    assert loaded.front_relief.bezier_contours == project.front_relief.bezier_contours
    assert loaded.front_relief.lock_confirmed_regions is False
    assert loaded.front_relief.adaptive_mesh_enabled is True

    source_path = tmp_path / "art.png"
    image = Image.new("RGBA", (48, 48), (255, 255, 255, 255))
    ImageDraw.Draw(image).ellipse((12, 12, 36, 36), fill=(25, 25, 25, 255))
    image.save(source_path)
    preview_dir = tmp_path / "review"
    parameters = ReliefParameters(
        mask_mode="alpha",
        crop_to_foreground=False,
        min_component_pixels=1,
        adaptive_mesh_enabled=True,
        adaptive_coarse_cell_px=8,
    )

    result = build_single_side_relief(
        source_path,
        tmp_path / "model.obj",
        parameters,
        preview_dir=preview_dir,
    )

    paths = result.report["preview_paths"]
    assert Path(paths["semantic_region_preview"]).is_file()
    assert Path(paths["confidence_heatmap_preview"]).is_file()
    assert Path(paths["mask_preview"]).is_file()
    assert result.report["adaptive_mesh"]["adaptive"] is True
    assert result.report["recognition_uncertainty"]["interpretation"].endswith("not probabilities")
