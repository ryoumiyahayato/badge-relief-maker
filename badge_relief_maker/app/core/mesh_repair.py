"""Lightweight mesh repair helpers for the MVP pipeline."""

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


def face_count(faces):
    """Return the number of mesh faces.

    Kept for compatibility with the earlier placeholder module.
    """
    return int(len(_as_faces(faces)))


def remove_invalid_faces(vertices, faces):
    """Remove faces that do not reference valid vertex indices."""
    vertices = _as_vertices(vertices)
    faces = _as_faces(faces)
    if len(faces) == 0:
        return faces, 0
    valid = np.all((faces >= 0) & (faces < len(vertices)), axis=1)
    return faces[valid], int(len(faces) - int(valid.sum()))


def triangle_areas(vertices, faces):
    """Return triangle areas for triangular faces."""
    vertices = _as_vertices(vertices)
    faces = _as_faces(faces)
    if len(faces) == 0:
        return np.zeros((0,), dtype=float)
    a = vertices[faces[:, 0]]
    b = vertices[faces[:, 1]]
    c = vertices[faces[:, 2]]
    return np.linalg.norm(np.cross(b - a, c - a), axis=1) * 0.5


def remove_zero_area_faces(vertices, faces, epsilon=1e-12):
    """Remove faces whose geometric area is effectively zero."""
    faces = _as_faces(faces)
    if len(faces) == 0:
        return faces, 0
    areas = triangle_areas(vertices, faces)
    keep = areas > float(epsilon)
    return faces[keep], int(len(faces) - int(keep.sum()))


def remove_duplicate_faces(faces):
    """Remove duplicate triangles regardless of winding order."""
    faces = _as_faces(faces)
    if len(faces) == 0:
        return faces, 0
    keys = np.sort(faces, axis=1)
    _, unique_indices = np.unique(keys, axis=0, return_index=True)
    unique_indices = np.sort(unique_indices)
    return faces[unique_indices], int(len(faces) - len(unique_indices))


def remove_unreferenced_vertices(vertices, faces):
    """Remove vertices that are not used by any face and remap faces."""
    vertices = _as_vertices(vertices)
    faces = _as_faces(faces)
    if len(vertices) == 0 or len(faces) == 0:
        return np.zeros((0, 3), dtype=float), np.zeros((0, 3), dtype=np.int64), int(len(vertices))

    used = np.unique(faces.reshape(-1))
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used), dtype=np.int64)
    return vertices[used], remap[faces], int(len(vertices) - len(used))


def remove_duplicate_vertices(vertices, faces):
    """Remove duplicate vertices and remap faces.

    Kept for compatibility with the earlier placeholder module.
    """
    vertices = _as_vertices(vertices)
    faces = _as_faces(faces)
    if len(vertices) == 0:
        return vertices, faces
    unique, inverse = np.unique(vertices, axis=0, return_inverse=True)
    return unique, inverse[faces] if len(faces) else faces


def repair_mesh_basic(vertices, faces):
    """Run conservative mesh cleanup and return repair metadata.

    This does not fill holes or solve complex self-intersections. It only removes
    invalid faces, zero-area faces, duplicate faces and unreferenced vertices.
    """
    vertices = _as_vertices(vertices)
    faces = _as_faces(faces)

    faces, invalid_faces_removed = remove_invalid_faces(vertices, faces)
    faces, zero_area_faces_removed = remove_zero_area_faces(vertices, faces)
    faces, duplicate_faces_removed = remove_duplicate_faces(faces)
    vertices, faces, unreferenced_vertices_removed = remove_unreferenced_vertices(vertices, faces)

    report = {
        "invalid_faces_removed": int(invalid_faces_removed),
        "zero_area_faces_removed": int(zero_area_faces_removed),
        "duplicate_faces_removed": int(duplicate_faces_removed),
        "unreferenced_vertices_removed": int(unreferenced_vertices_removed),
    }
    return vertices, faces, report
