import numpy as np

from badge_relief_maker.app.core.manufacturability_check import basic_report, face_geometry_report


def test_face_geometry_report_counts_orientation_and_area():
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    faces = np.asarray(
        [
            [0, 1, 2],
            [0, 2, 1],
            [0, 3, 1],
        ],
        dtype=np.int64,
    )

    report = face_geometry_report(vertices, faces)

    assert report["valid_face_count"] == 3
    assert report["invalid_face_count"] == 0
    assert report["zero_area_face_count"] == 0
    assert report["up_facing_face_count"] == 1
    assert report["down_facing_face_count"] == 1
    assert report["side_facing_face_count"] == 1
    assert report["total_surface_area_mm2"] > 0.0


def test_basic_report_warns_about_invalid_and_zero_area_faces():
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=float,
    )
    faces = np.asarray(
        [
            [0, 1, 2],
            [0, 0, 1],
            [0, 1, 99],
        ],
        dtype=np.int64,
    )

    report = basic_report(vertices, faces)

    assert report["face_geometry"]["invalid_face_count"] == 1
    assert report["face_geometry"]["zero_area_face_count"] == 1
    assert "invalid face references detected" in report["warnings"]
    assert "zero-area faces detected" in report["warnings"]
