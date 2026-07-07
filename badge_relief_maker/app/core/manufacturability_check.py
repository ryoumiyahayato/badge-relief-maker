"""Basic manufacturability report helpers."""

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


def basic_report(vertices, faces, minimum_thickness_mm=None, max_recommended_faces=200000):
    """Return a simple mesh diagnostic report.

    These checks are advisory only. They do not prove the model is ready for
    manufacturing, but they provide enough information for the early GUI and
    CLI to warn about obvious risks.
    """
    vertex_count = int(len(vertices))
    face_count = int(len(faces))
    bounds = mesh_bounds(vertices)
    warnings = []

    if vertex_count == 0 or face_count == 0:
        warnings.append("empty mesh")
    if face_count > int(max_recommended_faces):
        warnings.append("face count is high for the MVP pipeline")
    if minimum_thickness_mm is not None and bounds["size_z"] < float(minimum_thickness_mm):
        warnings.append("estimated total thickness is below the minimum thickness setting")

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
        "warnings": warnings,
        "watertight_check": "not implemented",
        "thin_region_check": "not implemented",
    }
