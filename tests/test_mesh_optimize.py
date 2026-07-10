import numpy as np
import pytest

from badge_relief_maker.app.core.mesh_optimize import optimize_mesh


def test_optimize_mesh_deduplicates_vertices_and_drops_invalid_faces():
    vertices = np.asarray(
        [[0, 0, 0], [1, 0, 0], [1, 0, 0], [0, 1, 0]],
        dtype=float,
    )
    faces = np.asarray([[0, 1, 3], [0, 2, 3], [0, 1, 99]], dtype=np.int64)

    optimized_vertices, optimized_faces = optimize_mesh(vertices, faces)

    assert optimized_vertices.shape == (3, 3)
    assert optimized_faces.shape == (2, 3)
    assert optimized_faces.max() < len(optimized_vertices)


def test_optimize_mesh_rejects_malformed_arrays():
    with pytest.raises(ValueError, match="vertices must be an Nx3 array"):
        optimize_mesh([0, 0, 0], [[0, 1, 2]])

    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    with pytest.raises(ValueError, match="faces must be an Nx3 array"):
        optimize_mesh(vertices, [[0, 1, 2, 3]])


def test_optimize_mesh_rejects_non_integer_faces_and_non_finite_vertices():
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    with pytest.raises(ValueError, match="faces must contain finite integer indices"):
        optimize_mesh(vertices, [[0, 1.5, 2]])

    bad_vertices = np.asarray([[0, 0, 0], [np.inf, 0, 0], [0, 1, 0]], dtype=float)
    with pytest.raises(ValueError, match="vertices contain non-finite coordinates"):
        optimize_mesh(bad_vertices, [[0, 1, 2]])
