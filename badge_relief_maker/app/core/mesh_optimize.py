"""Small mesh optimization helpers."""

import numpy as np


def _as_vertices(vertices):
    vertices = np.asarray(vertices, dtype=float)
    if vertices.size == 0:
        return np.zeros((0, 3), dtype=float)
    return vertices.reshape((-1, 3))


def _as_faces(faces):
    faces = np.asarray(faces, dtype=np.int64)
    if faces.size == 0:
        return np.zeros((0, 3), dtype=np.int64)
    return faces.reshape((-1, 3))


def deduplicate_vertices(vertices, faces, precision=6):
    """Merge identical or near-identical vertices and remap faces.

    This is a simple deterministic cleanup step for the MVP mesh. It rounds
    vertex coordinates to the requested precision before grouping them.
    """
    vertices = _as_vertices(vertices)
    faces = _as_faces(faces)
    if len(vertices) == 0:
        return vertices, faces

    rounded = np.round(vertices.astype(float), int(precision))
    unique_vertices, inverse = np.unique(rounded, axis=0, return_inverse=True)
    remapped_faces = inverse[faces] if len(faces) else faces
    return unique_vertices.astype(float), remapped_faces.astype(np.int64)


def remove_degenerate_faces(vertices, faces):
    """Remove faces that reference the same vertex more than once."""
    vertices = _as_vertices(vertices)
    faces = _as_faces(faces)
    if len(faces) == 0:
        return vertices, faces
    keep = []
    for face in faces:
        a, b, c = face
        keep.append(a != b and b != c and a != c)
    return vertices, faces[np.asarray(keep, dtype=bool)]


def optimize_mesh(vertices, faces, precision=6):
    """Run minimal mesh cleanup for the MVP."""
    vertices, faces = deduplicate_vertices(vertices, faces, precision=precision)
    vertices, faces = remove_degenerate_faces(vertices, faces)
    return vertices, faces
