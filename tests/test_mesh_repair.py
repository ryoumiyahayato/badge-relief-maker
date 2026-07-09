import numpy as np
import pytest

from badge_relief_maker.app.core.mesh_repair import (
    face_count,
    remove_unreferenced_vertices,
    repair_mesh_basic,
    triangle_areas,
)


def test_repair_mesh_basic_removes_invalid_zero_duplicate_and_unreferenced():
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [5.0, 5.0, 5.0],
        ],
        dtype=float,
    )
    faces = np.asarray(
        [
            [0, 1, 2],
            [0, 2, 1],
            [0, 0, 1],
            [0, 1, 99],
        ],
        dtype=np.int64,
    )

    repaired_vertices, repaired_faces, report = repair_mesh_basic(vertices, faces)

    assert repaired_vertices.shape == (3, 3)
    assert repaired_faces.shape == (1, 3)
    assert report["invalid_faces_removed"] == 1
    assert report["zero_area_faces_removed"] == 1
    assert report["duplicate_faces_removed"] == 1
    assert report["unreferenced_vertices_removed"] == 1


def test_repair_mesh_rejects_malformed_vertex_array():
    with pytest.raises(ValueError, match="vertices must be an Nx3 array"):
        repair_mesh_basic([0, 0, 0], [[0, 1, 2]])


def test_repair_mesh_rejects_malformed_face_array():
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)

    with pytest.raises(ValueError, match="faces must be an Nx3 array"):
        repair_mesh_basic(vertices, [[0, 1, 2, 0]])


def test_repair_mesh_rejects_non_integer_face_indices():
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)

    with pytest.raises(ValueError, match="faces must contain finite integer indices"):
        repair_mesh_basic(vertices, [[0.0, 1.5, 2.0]])


def test_face_count_rejects_flat_face_array():
    with pytest.raises(ValueError, match="faces must be an Nx3 array"):
        face_count([0, 1, 2])


def test_triangle_areas_ignores_invalid_face_references():
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.asarray([[0, 1, 2], [0, 1, 99]], dtype=np.int64)

    areas = triangle_areas(vertices, faces)

    assert areas.shape == (1,)
    assert float(areas[0]) == 0.5


def test_remove_unreferenced_vertices_drops_invalid_faces_without_crashing():
    vertices = np.asarray(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [9, 9, 9]],
        dtype=float,
    )
    faces = np.asarray([[0, 1, 2], [0, 1, 99]], dtype=np.int64)

    repaired_vertices, repaired_faces, removed = remove_unreferenced_vertices(vertices, faces)

    assert repaired_vertices.shape == (3, 3)
    assert repaired_faces.tolist() == [[0, 1, 2]]
    assert removed == 1
