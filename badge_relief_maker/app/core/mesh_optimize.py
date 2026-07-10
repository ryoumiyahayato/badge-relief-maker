"""Small mesh optimization helpers."""

import numpy as np


def _as_vertices(vertices):
    try:
        vertices = np.asarray(vertices, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("vertices must be an Nx3 array") from exc
    if vertices.size == 0:
        return np.zeros((0, 3), dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError("vertices must be an Nx3 array")
    if not np.isfinite(vertices).all():
        raise ValueError("vertices contain non-finite coordinates")
    return vertices


def _as_faces(faces):
    try:
        values = np.asarray(faces, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("faces must be an Nx3 array") from exc
    if values.size == 0:
        return np.zeros((0, 3), dtype=np.int64)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("faces must be an Nx3 array")
    if not np.isfinite(values).all() or not np.equal(values, np.rint(values)).all():
        raise ValueError("faces must contain finite integer indices")
    return values.astype(np.int64)


def _valid_faces(vertices, faces):
    if len(faces) == 0:
        return faces
    valid = np.all((faces >= 0) & (faces < len(vertices)), axis=1)
    return faces[valid]


def deduplicate_vertices(vertices, faces, precision=6):
    """Merge identical or near-identical vertices and remap valid faces."""
    vertices = _as_vertices(vertices)
    faces = _valid_faces(vertices, _as_faces(faces))
    if len(vertices) == 0:
        return vertices, np.zeros((0, 3), dtype=np.int64)

    rounded = np.round(vertices.astype(float), int(precision))
    unique_vertices, inverse = np.unique(rounded, axis=0, return_inverse=True)
    remapped_faces = inverse[faces] if len(faces) else faces
    return unique_vertices.astype(float), remapped_faces.astype(np.int64)


def remove_degenerate_faces(vertices, faces):
    """Remove invalid faces and faces that repeat a vertex index."""
    vertices = _as_vertices(vertices)
    faces = _valid_faces(vertices, _as_faces(faces))
    if len(faces) == 0:
        return vertices, faces
    keep = np.asarray([a != b and b != c and a != c for a, b, c in faces], dtype=bool)
    return vertices, faces[keep]


def optimize_mesh(vertices, faces, precision=6):
    """Run deterministic vertex deduplication and degenerate-face cleanup."""
    vertices, faces = deduplicate_vertices(vertices, faces, precision=precision)
    vertices, faces = remove_degenerate_faces(vertices, faces)
    return vertices, faces
