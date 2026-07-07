"""Small mesh optimization helpers."""

import numpy as np


def deduplicate_vertices(vertices, faces, precision=6):
    """Merge identical or near-identical vertices and remap faces.

    This is a simple deterministic cleanup step for the MVP mesh. It rounds
    vertex coordinates to the requested precision before grouping them.
    """
    if len(vertices) == 0:
        return vertices, faces

    rounded = np.round(vertices.astype(float), int(precision))
    unique_vertices, inverse = np.unique(rounded, axis=0, return_inverse=True)
    remapped_faces = inverse[faces]
    return unique_vertices.astype(float), remapped_faces.astype(np.int64)


def remove_degenerate_faces(vertices, faces):
    """Remove faces that reference the same vertex more than once."""
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
