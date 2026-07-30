"""Small mesh optimization helpers."""

import numpy as np

from .mesh_data import as_faces, as_vertices, valid_face_mask


def deduplicate_vertices(vertices, faces, precision=6):
    """Merge identical or near-identical vertices and remap valid faces."""
    vertices = as_vertices(vertices)
    faces = as_faces(faces)
    faces = faces[valid_face_mask(len(vertices), faces)]
    if len(vertices) == 0:
        return vertices, np.zeros((0, 3), dtype=np.int64)

    rounded = np.round(vertices.astype(float), int(precision))
    unique_vertices, inverse = np.unique(rounded, axis=0, return_inverse=True)
    remapped_faces = inverse[faces] if len(faces) else faces
    return unique_vertices.astype(float), remapped_faces.astype(np.int64)


def remove_degenerate_faces(vertices, faces):
    """Remove invalid faces and faces that repeat a vertex index."""
    vertices = as_vertices(vertices)
    faces = as_faces(faces)
    faces = faces[valid_face_mask(len(vertices), faces)]
    if len(faces) == 0:
        return vertices, faces
    keep = np.asarray([a != b and b != c and a != c for a, b, c in faces], dtype=bool)
    return vertices, faces[keep]


def optimize_mesh(vertices, faces, precision=6):
    """Run deterministic vertex deduplication and degenerate-face cleanup."""
    vertices, faces = deduplicate_vertices(vertices, faces, precision=precision)
    vertices, faces = remove_degenerate_faces(vertices, faces)
    return vertices, faces
