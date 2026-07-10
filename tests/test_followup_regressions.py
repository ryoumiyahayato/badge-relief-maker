import numpy as np
import pytest

from badge_relief_maker.app.core.height_markers import apply_manual_height_markers
from badge_relief_maker.app.core.manufacturability_check import (
    basic_report,
    connected_component_report,
    face_geometry_report,
    mesh_bounds,
)
from badge_relief_maker.app.core.marker_transform import transform_manual_height_markers
from badge_relief_maker.app.core.mask_generator import foreground_mask


def test_auto_mask_uses_luminance_for_uniform_semitransparent_alpha():
    rgba = np.full((5, 5, 4), 255, dtype=np.uint8)
    rgba[:, :, 3] = 128
    rgba[2, 2, :3] = 0

    mask, mode = foreground_mask(rgba, mode="auto", luminance_threshold=20)

    assert mode == "luminance"
    assert int(mask.sum()) == 1
    assert mask[2, 2]


def test_auto_mask_preserves_fully_transparent_empty_image():
    rgba = np.zeros((4, 4, 4), dtype=np.uint8)
    rgba[1:3, 1:3, :3] = 255

    mask, mode = foreground_mask(rgba, mode="auto")

    assert mode == "alpha"
    assert not mask.any()


def test_auto_mask_uses_variable_alpha_when_informative():
    rgba = np.full((4, 4, 4), 255, dtype=np.uint8)
    rgba[:, :, 3] = 0
    rgba[1:3, 1:3, 3] = 255

    mask, mode = foreground_mask(rgba, mode="auto")

    assert mode == "alpha"
    assert int(mask.sum()) == 4


def test_auto_mask_rejects_non_rgba_input():
    with pytest.raises(ValueError, match="expected rgba image"):
        foreground_mask(np.zeros((4, 4, 3), dtype=np.uint8), mode="auto")


def test_marker_transform_ignores_invalid_numeric_geometry():
    transformed = transform_manual_height_markers(
        ({"marker_type": "height", "x": "bad", "y": 2, "radius_px": 1, "height": 0.5},),
        original_shape=(10, 10),
        crop_box=None,
        cropped_shape=(10, 10),
        resized_shape=(5, 5),
    )

    assert transformed == ()


def test_marker_transform_ignores_invalid_processed_marker_before_requested_count():
    transformed = transform_manual_height_markers(
        ({"marker_type": "height", "coordinate_space": "processed", "x": "bad", "y": 2, "height": 0.5},),
        original_shape=(10, 10),
        crop_box=None,
        cropped_shape=(10, 10),
        resized_shape=(5, 5),
    )
    _, report = apply_manual_height_markers(np.zeros((5, 5)), np.ones((5, 5), dtype=bool), transformed)

    assert transformed == ()
    assert report["requested_marker_count"] == 0


def test_marker_transform_ignores_invalid_polygon_without_aborting_following_marker():
    transformed = transform_manual_height_markers(
        (
            {"marker_type": "height", "shape": "polygon", "points": [(0, 0), (1, "bad"), (1, 1)], "height": 0.5},
            {"marker_type": "height", "x": 0.5, "y": 0.5, "radius_px": 1, "height": 0.4},
        ),
        original_shape=(10, 10),
        crop_box=None,
        cropped_shape=(10, 10),
        resized_shape=(5, 5),
    )

    assert len(transformed) == 1
    assert transformed[0]["height"] == 0.4


def test_face_geometry_counts_faces_as_invalid_when_vertex_array_is_empty():
    report = face_geometry_report(np.zeros((0, 3)), np.asarray([[0, 1, 2]], dtype=np.int64))

    assert report["valid_face_count"] == 0
    assert report["invalid_face_count"] == 1
    assert report["malformed_face_array"] is False


def test_face_geometry_keeps_malformed_flag_with_empty_vertices():
    report = face_geometry_report(np.zeros((0, 3)), np.asarray([0, 1, 2], dtype=np.int64))

    assert report["invalid_face_count"] == 1
    assert report["malformed_face_array"] is True


def test_mesh_bounds_rejects_scalar_vertices_with_clear_error():
    with pytest.raises(ValueError, match="finite Nx3"):
        mesh_bounds(1.0)


def test_connected_component_report_and_warning():
    vertices = np.asarray(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [10, 0, 0],
            [11, 0, 0],
            [10, 1, 0],
        ],
        dtype=float,
    )
    faces = np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int64)

    components = connected_component_report(vertices, faces)
    report = basic_report(vertices, faces)

    assert components["component_count"] == 2
    assert components["component_face_counts"] == [1, 1]
    assert components["largest_component_face_count"] == 1
    assert components["closed_oriented_component_count"] == 0
    assert components["open_or_unoriented_component_count"] == 2
    assert "multiple disconnected mesh components detected" in report["warnings"]


def test_component_report_detects_inward_closed_component_without_volume_cancellation():
    outward_vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    outward_faces = np.asarray(
        [
            [0, 2, 1],
            [0, 1, 3],
            [0, 3, 2],
            [1, 2, 3],
        ],
        dtype=np.int64,
    )
    inward_vertices = outward_vertices + np.asarray([10.0, 0.0, 0.0])
    inward_faces = outward_faces[:, [0, 2, 1]] + 4
    vertices = np.vstack((outward_vertices, inward_vertices))
    faces = np.vstack((outward_faces, inward_faces))

    components = connected_component_report(vertices, faces)
    report = basic_report(vertices, faces)

    assert components["component_count"] == 2
    assert components["component_face_counts"] == [4, 4]
    assert components["component_closed_oriented_flags"] == [True, True]
    assert components["closed_oriented_component_count"] == 2
    assert components["inward_closed_component_count"] == 1
    assert components["component_signed_volumes_mm3"][0] > 0.0
    assert components["component_signed_volumes_mm3"][1] < 0.0
    assert "one or more closed mesh components appear inward" in report["warnings"]
