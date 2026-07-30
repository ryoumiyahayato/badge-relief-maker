"""Strict mesh-array normalization shared by repair, optimize and export."""

import numpy as np


def as_nx3_array(values, dtype, name):
    """Normalize an empty or Nx3 array without applying semantic validation."""
    try:
        data = np.asarray(values, dtype=dtype)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an Nx3 array") from exc
    if data.size == 0:
        return np.zeros((0, 3), dtype=dtype)
    if data.ndim != 2 or data.shape[1] != 3:
        raise ValueError(f"{name} must be an Nx3 array")
    return data


def as_vertices(vertices, dtype=float):
    """Return a finite Nx3 vertex array."""
    values = as_nx3_array(vertices, dtype, "vertices")
    if not np.isfinite(values).all():
        raise ValueError("vertices contain non-finite coordinates")
    return values


def as_faces(faces):
    """Return an Nx3 integer face-index array."""
    values = as_nx3_array(faces, float, "faces")
    if not np.isfinite(values).all() or not np.equal(values, np.rint(values)).all():
        raise ValueError("faces must contain finite integer indices")
    return values.astype(np.int64)


def valid_face_mask(vertex_count, faces):
    """Return a row mask selecting faces whose indices address the vertex array."""
    return np.all((faces >= 0) & (faces < int(vertex_count)), axis=1)


def signed_volume(vertices, faces):
    """Return the oriented volume enclosed by triangular faces."""
    if len(faces) == 0:
        return 0.0
    first = vertices[faces[:, 0]]
    second = vertices[faces[:, 1]]
    third = vertices[faces[:, 2]]
    return float(np.einsum("ij,ij->i", first, np.cross(second, third)).sum() / 6.0)
