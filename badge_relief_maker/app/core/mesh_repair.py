"""Lightweight mesh repair helpers for the MVP pipeline."""

import numpy as np
from collections import defaultdict, deque


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
        face_values = np.asarray(faces, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("faces must be an Nx3 array") from exc
    if face_values.size == 0:
        return np.zeros((0, 3), dtype=np.int64)
    if face_values.ndim != 2 or face_values.shape[1] != 3:
        raise ValueError("faces must be an Nx3 array")
    if not np.isfinite(face_values).all() or not np.equal(face_values, np.rint(face_values)).all():
        raise ValueError("faces must contain finite integer indices")
    return face_values.astype(np.int64)


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
    faces, _ = remove_invalid_faces(vertices, faces)
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
    valid_faces, invalid_removed = remove_invalid_faces(vertices, faces)
    if len(valid_faces) == 0:
        return valid_faces, int(invalid_removed)
    areas = triangle_areas(vertices, valid_faces)
    keep = areas > float(epsilon)
    return valid_faces[keep], int(invalid_removed + len(valid_faces) - int(keep.sum()))


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
    """Remove vertices that are not used by valid faces and remap faces."""
    vertices = _as_vertices(vertices)
    faces, _ = remove_invalid_faces(vertices, faces)
    if len(vertices) == 0 or len(faces) == 0:
        return np.zeros((0, 3), dtype=float), np.zeros((0, 3), dtype=np.int64), int(len(vertices))

    used = np.unique(faces.reshape(-1))
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used), dtype=np.int64)
    return vertices[used], remap[faces], int(len(vertices) - len(used))


def remove_duplicate_vertices(vertices, faces):
    """Remove duplicate vertices and remap valid faces.

    Kept for compatibility with the earlier placeholder module.
    """
    vertices = _as_vertices(vertices)
    faces, _ = remove_invalid_faces(vertices, faces)
    if len(vertices) == 0:
        return vertices, faces
    unique, inverse = np.unique(vertices, axis=0, return_inverse=True)
    return unique, inverse[faces] if len(faces) else faces


def _signed_volume(vertices, faces):
    if len(faces) == 0:
        return 0.0
    first = vertices[faces[:, 0]]
    second = vertices[faces[:, 1]]
    third = vertices[faces[:, 2]]
    return float(np.einsum("ij,ij->i", first, np.cross(second, third)).sum() / 6.0)


def orient_closed_components_outward(vertices, faces):
    """Propagate consistent winding and reverse inward closed components."""
    vertices = _as_vertices(vertices)
    faces = _as_faces(faces).copy()
    edge_uses = defaultdict(list)
    for face_index, (a, b, c) in enumerate(faces):
        for left, right in ((a, b), (b, c), (c, a)):
            edge_uses[tuple(sorted((int(left), int(right))))].append((face_index, int(left), int(right)))

    adjacency = defaultdict(list)
    for uses in edge_uses.values():
        if len(uses) != 2:
            continue
        first, second = uses
        same_direction = first[1] == second[1] and first[2] == second[2]
        adjacency[first[0]].append((second[0], same_direction))
        adjacency[second[0]].append((first[0], same_direction))

    flip = np.full(len(faces), -1, dtype=np.int8)
    components = []
    conflicts = 0
    for start in range(len(faces)):
        if flip[start] >= 0:
            continue
        flip[start] = 0
        queue = deque([start])
        component = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor, same_direction in adjacency[current]:
                expected = int(flip[current]) ^ int(same_direction)
                if flip[neighbor] < 0:
                    flip[neighbor] = expected
                    queue.append(neighbor)
                elif int(flip[neighbor]) != expected:
                    conflicts += 1
        components.append(component)

    propagated_flips = int(np.count_nonzero(flip == 1))
    faces[flip == 1] = faces[flip == 1][:, [0, 2, 1]]
    reversed_components = 0
    for component in components:
        component_faces = faces[np.asarray(component, dtype=np.int64)]
        local_edges = defaultdict(int)
        for a, b, c in component_faces:
            for left, right in ((a, b), (b, c), (c, a)):
                local_edges[tuple(sorted((int(left), int(right))))] += 1
        closed = bool(local_edges) and all(count == 2 for count in local_edges.values())
        if closed and _signed_volume(vertices, component_faces) < 0.0:
            indices = np.asarray(component, dtype=np.int64)
            faces[indices] = faces[indices][:, [0, 2, 1]]
            reversed_components += 1
    return vertices, faces, {
        "propagated_face_flips": propagated_flips,
        "reversed_inward_components": int(reversed_components),
        "orientation_conflict_count": int(conflicts),
    }


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
    vertices, faces, orientation_report = orient_closed_components_outward(vertices, faces)

    report = {
        "invalid_faces_removed": int(invalid_faces_removed),
        "zero_area_faces_removed": int(zero_area_faces_removed),
        "duplicate_faces_removed": int(duplicate_faces_removed),
        "unreferenced_vertices_removed": int(unreferenced_vertices_removed),
        **orientation_report,
    }
    return vertices, faces, report
