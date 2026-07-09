"""Basic manufacturability report helpers."""

from collections import Counter

import numpy as np


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


def edge_usage_report(faces):
    """Return simple open-edge and non-manifold edge diagnostics.

    The check assumes triangular faces. It is intentionally lightweight and is
    suitable for warnings, not for proving production-grade mesh validity.
    """
    faces = np.asarray(faces, dtype=np.int64)
    if len(faces) == 0:
        return {
            "unique_edge_count": 0,
            "boundary_edge_count": 0,
            "non_manifold_edge_count": 0,
            "closed_edge_manifold": False,
        }

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
    }


def basic_report(vertices, faces, minimum_thickness_mm=None, max_recommended_faces=200000):
    """Return a simple mesh diagnostic report.

    These checks are advisory only. They do not prove the model is ready for
    manufacturing, but they provide enough information for the early GUI and
    CLI to warn about obvious risks.
    """
    vertex_count = int(len(vertices))
    face_count = int(len(faces))
    bounds = mesh_bounds(vertices)
    topology = edge_usage_report(faces)
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
        "warnings": warnings,
        "watertight_check": "edge manifold heuristic only",
        "thin_region_check": "not implemented",
    }
