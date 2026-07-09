"""Basic manufacturability report helpers."""

from collections import Counter

import numpy as np


_MALFORMED_FACE_WARNING = "malformed face array detected"


def _empty_bbox():
    return {
        "min_x": None,
        "min_y": None,
        "min_z": None,
        "max_x": None,
        "max_y": None,
        "max_z": None,
        "size_x": 0.0,
        "size_y": 0.0,
        "size_z": 0.0,
    }


def mesh_bounds(vertices):
    """Return a simple bounding box report for vertices."""
    if len(vertices) == 0:
        return _empty_bbox()
    data = np.asarray(vertices, dtype=float)
    mins = data.min(axis=0)
    maxs = data.max(axis=0)
    sizes = maxs - mins
    return {
        "min_x": float(mins[0]),
        "min_y": float(mins[1]),
        "min_z": float(mins[2]),
        "max_x": float(maxs[0]),
        "max_y": float(maxs[1]),
        "max_z": float(maxs[2]),
        "size_x": float(sizes[0]),
        "size_y": float(sizes[1]),
        "size_z": float(sizes[2]),
    }


def _empty_topology_report(malformed_face_array=False):
    return {
        "unique_edge_count": 0,
        "boundary_edge_count": 0,
        "non_manifold_edge_count": 0,
        "closed_edge_manifold": False,
        "malformed_face_array": bool(malformed_face_array),
    }


def _empty_face_geometry_report(invalid_face_count=0, malformed_face_array=False):
    return {
        "valid_face_count": 0,
        "invalid_face_count": int(invalid_face_count),
        "zero_area_face_count": 0,
        "total_surface_area_mm2": 0.0,
        "min_face_area_mm2": 0.0,
        "max_face_area_mm2": 0.0,
        "up_facing_face_count": 0,
        "down_facing_face_count": 0,
        "side_facing_face_count": 0,
        "malformed_face_array": bool(malformed_face_array),
    }


def _faces_array(faces):
    try:
        return np.asarray(faces, dtype=np.int64)
    except (TypeError, ValueError):
        return None


def _is_row_like(value):
    if isinstance(value, (str, bytes)):
        return False
    try:
        len(value)
    except TypeError:
        return False
    return True


def _face_row_count(faces):
    faces = np.asarray(faces, dtype=object)
    if faces.ndim == 0:
        return 0
    if faces.ndim == 1:
        if faces.size == 0:
            return 0
        return int(len(faces)) if _is_row_like(faces[0]) else 1
    return int(len(faces))


def _is_triangular_face_array(faces):
    return faces is not None and faces.ndim == 2 and faces.shape[1] == 3


def edge_usage_report(faces):
    """Return simple open-edge and non-manifold edge diagnostics.

    The check assumes triangular faces. It is intentionally lightweight and is
    suitable for warnings, not for proving production-grade mesh validity.
    """
    faces = _faces_array(faces)
    if faces is None:
        return _empty_topology_report(malformed_face_array=True)
    if faces.size == 0:
        return _empty_topology_report()
    if not _is_triangular_face_array(faces):
        return _empty_topology_report(malformed_face_array=True)

    counter = Counter()
    for a, b, c in faces:
        for u, v in [(a, b), (b, c), (c, a)]:
            edge = tuple(sorted((int(u), int(v))))
            counter[edge] += 1

    boundary_edges = sum(1 for count in counter.values() if count == 1)
    non_manifold_edges = sum(1 for count in counter.values() if count > 2)
    return {
        "unique_edge_count": int(len(counter)),
        "boundary_edge_count": int(boundary_edges),
        "non_manifold_edge_count": int(non_manifold_edges),
        "closed_edge_manifold": bool(boundary_edges == 0 and non_manifold_edges == 0 and len(counter) > 0),
        "malformed_face_array": False,
    }


def face_geometry_report(vertices, faces, zero_area_epsilon=1e-12):
    """Return lightweight triangle area and normal-orientation diagnostics."""
    vertices = np.asarray(vertices, dtype=float)
    faces = _faces_array(faces)
    if faces is None:
        return _empty_face_geometry_report(invalid_face_count=1, malformed_face_array=True)
    if len(vertices) == 0 or faces.size == 0:
        return _empty_face_geometry_report()
    if not _is_triangular_face_array(faces):
        return _empty_face_geometry_report(invalid_face_count=_face_row_count(faces), malformed_face_array=True)

    valid_mask = np.all((faces >= 0) & (faces < len(vertices)), axis=1)
    valid_faces = faces[valid_mask]
    invalid_count = int(len(faces) - len(valid_faces))
    if len(valid_faces) == 0:
        return _empty_face_geometry_report(invalid_face_count=invalid_count)

    p0 = vertices[valid_faces[:, 0]]
    p1 = vertices[valid_faces[:, 1]]
    p2 = vertices[valid_faces[:, 2]]
    normals = np.cross(p1 - p0, p2 - p0)
    double_areas = np.linalg.norm(normals, axis=1)
    areas = double_areas * 0.5
    nonzero = double_areas > float(zero_area_epsilon)
    zero_area_count = int(np.count_nonzero(~nonzero))

    up_count = 0
    down_count = 0
    side_count = 0
    if np.any(nonzero):
        unit_z = normals[nonzero, 2] / double_areas[nonzero]
        up_count = int(np.count_nonzero(unit_z > 0.5))
        down_count = int(np.count_nonzero(unit_z < -0.5))
        side_count = int(np.count_nonzero((unit_z >= -0.5) & (unit_z <= 0.5)))

    return {
        "valid_face_count": int(len(valid_faces)),
        "invalid_face_count": invalid_count,
        "zero_area_face_count": zero_area_count,
        "total_surface_area_mm2": float(areas.sum()),
        "min_face_area_mm2": float(areas.min()) if len(areas) else 0.0,
        "max_face_area_mm2": float(areas.max()) if len(areas) else 0.0,
        "up_facing_face_count": up_count,
        "down_facing_face_count": down_count,
        "side_facing_face_count": side_count,
        "malformed_face_array": False,
    }


def basic_report(vertices, faces, minimum_thickness_mm=None, max_recommended_faces=200000):
    """Return a simple mesh diagnostic report.

    These checks are advisory only. They do not prove the model is ready for
    manufacturing, but they provide enough information for the early GUI and
    CLI to warn about obvious risks.
    """
    vertex_count = int(len(vertices))
    face_count = _face_row_count(faces)
    bounds = mesh_bounds(vertices)
    topology = edge_usage_report(faces)
    face_geometry = face_geometry_report(vertices, faces)
    warnings = []

    if vertex_count == 0 or face_count == 0:
        warnings.append("empty mesh")
    if face_count > int(max_recommended_faces):
        warnings.append("face count is high for the MVP pipeline")
    if minimum_thickness_mm is not None and bounds["size_z"] < float(minimum_thickness_mm):
        warnings.append("estimated total thickness is below the minimum thickness setting")
    if topology["boundary_edge_count"] > 0:
        warnings.append("open boundary edges detected")
    if topology["non_manifold_edge_count"] > 0:
        warnings.append("non-manifold edges detected")
    if topology.get("malformed_face_array") or face_geometry.get("malformed_face_array"):
        warnings.append(_MALFORMED_FACE_WARNING)
    if face_geometry["invalid_face_count"] > 0:
        warnings.append("invalid face references detected")
    if face_geometry["zero_area_face_count"] > 0:
        warnings.append("zero-area faces detected")

    return {
        "vertex_count": vertex_count,
        "face_count": face_count,
        "bbox": bounds,
        "size_mm": {
            "x": bounds["size_x"],
            "y": bounds["size_y"],
            "z": bounds["size_z"],
        },
        "estimated_total_thickness_mm": bounds["size_z"],
        "minimum_thickness_mm": minimum_thickness_mm,
        "topology": topology,
        "face_geometry": face_geometry,
        "warnings": warnings,
        "watertight_check": "edge manifold heuristic only",
        "thin_region_check": "not implemented",
    }
