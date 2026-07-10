import numpy as np

from badge_relief_maker.app.core.manufacturability_check import basic_report
from badge_relief_maker.app.core.solid_builder import build_rectangular_relief_solid


def test_rectangular_relief_solid_is_closed_and_outward_oriented():
    heightmap = np.asarray([[0.25, 1.0]], dtype=float)

    vertices, faces = build_rectangular_relief_solid(heightmap, 80.0, 40.0, 2.0, 3.0)
    report = basic_report(vertices, faces)

    assert report["bbox"]["size_x"] == 80.0
    assert report["bbox"]["size_y"] == 40.0
    assert report["topology"]["closed_edge_manifold"] is True
    assert report["topology"]["closed_oriented_manifold"] is True
    assert report["topology"]["inconsistent_winding_edge_count"] == 0
    assert report["face_geometry"]["signed_volume_mm3"] > 0.0


def test_rectangular_relief_solid_supports_one_pixel_heightmap():
    vertices, faces = build_rectangular_relief_solid(np.asarray([[1.0]]), 10.0, 12.0, 2.0, 3.0)
    report = basic_report(vertices, faces)

    assert len(vertices) == 8
    assert len(faces) == 12
    assert report["bbox"]["size_x"] == 10.0
    assert report["bbox"]["size_y"] == 12.0
    assert report["topology"]["closed_oriented_manifold"] is True
    assert report["face_geometry"]["signed_volume_mm3"] > 0.0
