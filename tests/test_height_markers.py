import numpy as np
from PIL import Image

from badge_relief_maker.app.core.height_markers import apply_manual_height_markers
from badge_relief_maker.app.core.project_build import build_front_relief_from_project_file
from badge_relief_maker.app.core.project_io import create_project, import_image_asset, save_project
from badge_relief_maker.app.core.project_model import ManualMarker
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief


def test_apply_manual_height_marker_sets_normalized_region():
    heightmap = np.ones((5, 5), dtype=float)
    mask = np.ones((5, 5), dtype=bool)

    result, report = apply_manual_height_markers(
        heightmap,
        mask,
        [
            {
                "marker_type": "height_override",
                "x": 0.5,
                "y": 0.5,
                "radius_px": 1,
                "height_normalized": 0.25,
            }
        ],
    )

    assert report["enabled"] is True
    assert report["requested_marker_count"] == 1
    assert report["applied_marker_count"] == 1
    assert report["affected_pixel_count"] == 5
    assert float(result[2, 2]) == 0.25
    assert float(result[0, 0]) == 1.0


def test_apply_manual_height_marker_ignores_invalid_marker():
    heightmap = np.ones((3, 3), dtype=float)
    mask = np.ones((3, 3), dtype=bool)

    result, report = apply_manual_height_markers(heightmap, mask, [{"marker_type": "note", "x": 0.5}])

    assert report["enabled"] is False
    assert report["ignored_marker_count"] == 1
    assert np.allclose(result, heightmap)


def test_apply_rectangular_height_marker_uses_shape_string_for_region():
    heightmap = np.zeros((5, 5), dtype=float)
    mask = np.ones((5, 5), dtype=bool)

    result, report = apply_manual_height_markers(
        heightmap,
        mask,
        [
            {
                "marker_type": "height",
                "shape": "rectangle",
                "x": 0.5,
                "y": 0.5,
                "width_px": 2,
                "height_px": 2,
                "height_normalized": 0.75,
            }
        ],
    )

    assert report["enabled"] is True
    assert report["applied_marker_count"] == 1
    assert report["affected_pixel_count"] == 9
    assert float(result[2, 2]) == 0.75
    assert float(result[0, 0]) == 0.0


def test_apply_manual_height_marker_add_and_subtract_operations():
    heightmap = np.full((3, 3), 0.5, dtype=float)
    mask = np.ones((3, 3), dtype=bool)

    raised, raise_report = apply_manual_height_markers(
        heightmap,
        mask,
        [{"marker_type": "height", "x": 0.5, "y": 0.5, "radius_px": 1, "operation": "add", "delta": 0.25}],
    )
    lowered, lower_report = apply_manual_height_markers(
        heightmap,
        mask,
        [{"marker_type": "height", "x": 0.5, "y": 0.5, "radius_px": 1, "operation": "subtract", "delta": 0.2}],
    )

    assert raise_report["applied_marker_count"] == 1
    assert lower_report["applied_marker_count"] == 1
    assert float(raised[1, 1]) == 0.75
    assert float(lowered[1, 1]) == 0.3
    assert float(raised[0, 0]) == 0.5
    assert float(lowered[0, 0]) == 0.5


def test_single_side_pipeline_reports_manual_height_marker(tmp_path):
    image_path = tmp_path / "front.png"
    Image.new("RGBA", (6, 6), (255, 255, 255, 255)).save(image_path)

    result = build_single_side_relief(
        image_path,
        None,
        ReliefParameters(
            crop_to_foreground=False,
            manual_height_markers=(
                {"marker_type": "height", "x": 0.5, "y": 0.5, "radius_px": 1, "height_normalized": 0.2},
            ),
        ),
    )

    assert result.report["manual_height"]["enabled"] is True
    assert result.report["manual_height"]["affected_pixel_count"] > 0
    assert "manual height markers were applied" in result.report["warnings"]


def test_project_manual_height_markers_are_passed_to_side_build(tmp_path):
    image_path = tmp_path / "front.png"
    Image.new("RGBA", (6, 6), (255, 255, 255, 255)).save(image_path)

    project = create_project("Manual Marker Project")
    project.manual_markers.append(
        ManualMarker(
            marker_type="height_override",
            target="front",
            data={"x": 0.5, "y": 0.5, "radius_px": 1, "height_normalized": 0.2},
        )
    )
    project_path = tmp_path / "manual_marker.medalproj"
    save_project(project, project_path)
    import_image_asset(project, project_path, image_path, "front")
    save_project(project, project_path)

    result = build_front_relief_from_project_file(project_path, export_format="obj", quality_mode="preview")

    assert result.report["manual_height"]["enabled"] is True
    assert result.report["manual_height"]["requested_marker_count"] == 1
    assert result.report["manual_height"]["affected_pixel_count"] > 0


def test_project_manual_marker_outer_metadata_overrides_conflicting_data(tmp_path):
    image_path = tmp_path / "front.png"
    Image.new("RGBA", (6, 6), (255, 255, 255, 255)).save(image_path)

    project = create_project("Conflicting Manual Marker Project")
    project.manual_markers.append(
        ManualMarker(
            marker_type="height_override",
            target="front",
            data={
                "marker_type": "note",
                "target": "back",
                "x": 0.5,
                "y": 0.5,
                "radius_px": 1,
                "height_normalized": 0.2,
            },
        )
    )
    project_path = tmp_path / "conflicting_manual_marker.medalproj"
    save_project(project, project_path)
    import_image_asset(project, project_path, image_path, "front")
    save_project(project, project_path)

    result = build_front_relief_from_project_file(project_path, export_format="obj", quality_mode="preview")

    assert result.report["manual_height"]["enabled"] is True
    assert result.report["manual_height"]["applied_marker_count"] == 1
    assert result.report["manual_height"]["ignored_marker_count"] == 0
