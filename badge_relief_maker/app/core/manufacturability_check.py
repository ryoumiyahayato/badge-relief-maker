"""Basic manufacturability report helpers."""

from collections import Counter

import numpy as np


_MALFORMED_FACE_WARNING = "malformed face array detected"
_MANUFACTURING_DISCLAIMER = (
    "Manufacturing checks are advisory only. A closed mesh can still contain thin walls, "
    "self-intersections, unsupported details or process-specific hazards."
)


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


def _vertices_array(vertices):
    try:
        values = np.asarray(vertices, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("vertices must be a finite Nx3 array") from exc
    if values.size == 0:
        return np.zeros((0, 3), dtype=float)
    if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
        raise ValueError("vertices must be a finite Nx3 array")
    return values


def mesh_bounds(vertices):
    """Return a simple bounding box report for vertices."""
    data = _vertices_array(vertices)
    if len(data) == 0:
        return _empty_bbox()
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
        "inconsistent_winding_edge_count": 0,
        "closed_edge_manifold": False,
        "closed_oriented_manifold": False,
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
        "signed_volume_mm3": 0.0,
        "absolute_volume_mm3": 0.0,
        "up_facing_face_count": 0,
        "down_facing_face_count": 0,
        "side_facing_face_count": 0,
        "malformed_face_array": bool(malformed_face_array),
    }


def _empty_component_report(invalid_face_count=0, malformed_face_array=False):
    return {
        "component_count": 0,
        "component_face_counts": [],
        "component_signed_volumes_mm3": [],
        "component_closed_oriented_flags": [],
        "component_reports": [],
        "largest_component_face_count": 0,
        "closed_oriented_component_count": 0,
        "inward_closed_component_count": 0,
        "open_or_unoriented_component_count": 0,
        "valid_face_count": 0,
        "invalid_face_count": int(invalid_face_count),
        "malformed_face_array": bool(malformed_face_array),
    }


def _faces_array(faces):
    try:
        values = np.asarray(faces, dtype=float)
    except (TypeError, ValueError):
        return None
    if values.size == 0:
        return np.zeros((0, 3), dtype=np.int64)
    if values.ndim != 2 or values.shape[1] != 3:
        return values
    if not np.isfinite(values).all() or not np.equal(values, np.rint(values)).all():
        return None
    return values.astype(np.int64)


def _is_row_like(value):
    if isinstance(value, (str, bytes)):
        return False
    try:
        len(value)
    except TypeError:
        return False
    return True


def _face_row_count(faces):
    try:
        faces = np.asarray(faces, dtype=object)
    except (TypeError, ValueError):
        return 1
    if faces.ndim == 0:
        return 0
    if faces.ndim == 1:
        if faces.size == 0:
            return 0
        return int(len(faces)) if _is_row_like(faces[0]) else 1
    return int(len(faces))


def _is_triangular_face_array(faces):
    return faces is not None and faces.ndim == 2 and faces.shape[1] == 3 and np.issubdtype(faces.dtype, np.integer)


def edge_usage_report(faces):
    """Return open-edge, non-manifold and winding diagnostics."""
    normalized_faces = _faces_array(faces)
    if normalized_faces is None:
        return _empty_topology_report(malformed_face_array=True)
    if normalized_faces.size == 0:
        return _empty_topology_report()
    if not _is_triangular_face_array(normalized_faces):
        return _empty_topology_report(malformed_face_array=True)

    undirected = Counter()
    directed = Counter()
    for a, b, c in normalized_faces:
        for u, v in [(a, b), (b, c), (c, a)]:
            u = int(u)
            v = int(v)
            undirected[tuple(sorted((u, v)))] += 1
            directed[(u, v)] += 1

    boundary_edges = sum(1 for count in undirected.values() if count == 1)
    non_manifold_edges = sum(1 for count in undirected.values() if count > 2)
    inconsistent_winding = 0
    for a, b in undirected:
        if undirected[(a, b)] == 2 and not (directed[(a, b)] == 1 and directed[(b, a)] == 1):
            inconsistent_winding += 1
    closed = boundary_edges == 0 and non_manifold_edges == 0 and len(undirected) > 0
    return {
        "unique_edge_count": int(len(undirected)),
        "boundary_edge_count": int(boundary_edges),
        "non_manifold_edge_count": int(non_manifold_edges),
        "inconsistent_winding_edge_count": int(inconsistent_winding),
        "closed_edge_manifold": bool(closed),
        "closed_oriented_manifold": bool(closed and inconsistent_winding == 0),
        "malformed_face_array": False,
    }


def _valid_faces(vertices, faces):
    valid_mask = np.all((faces >= 0) & (faces < len(vertices)), axis=1)
    return faces[valid_mask], int(len(faces) - int(valid_mask.sum()))


def _signed_volume(vertices, faces):
    if len(faces) == 0:
        return 0.0
    p0 = vertices[faces[:, 0]]
    p1 = vertices[faces[:, 1]]
    p2 = vertices[faces[:, 2]]
    return float(np.einsum("ij,ij->i", p0, np.cross(p1, p2)).sum() / 6.0)


def face_geometry_report(vertices, faces, zero_area_epsilon=1e-12):
    """Return triangle area, volume and normal-orientation diagnostics."""
    vertices = _vertices_array(vertices)
    malformed_row_count = _face_row_count(faces)
    normalized_faces = _faces_array(faces)
    if normalized_faces is None:
        return _empty_face_geometry_report(invalid_face_count=malformed_row_count, malformed_face_array=True)
    if normalized_faces.size == 0:
        return _empty_face_geometry_report()
    if not _is_triangular_face_array(normalized_faces):
        return _empty_face_geometry_report(invalid_face_count=malformed_row_count, malformed_face_array=True)

    valid_faces, invalid_count = _valid_faces(vertices, normalized_faces)
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
    signed_volume = _signed_volume(vertices, valid_faces)

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
        "signed_volume_mm3": signed_volume,
        "absolute_volume_mm3": abs(signed_volume),
        "up_facing_face_count": up_count,
        "down_facing_face_count": down_count,
        "side_facing_face_count": side_count,
        "malformed_face_array": False,
    }


def connected_component_report(vertices, faces):
    """Report face-connected components using shared vertex indices."""
    vertices = _vertices_array(vertices)
    malformed_row_count = _face_row_count(faces)
    normalized_faces = _faces_array(faces)
    if normalized_faces is None:
        return _empty_component_report(invalid_face_count=malformed_row_count, malformed_face_array=True)
    if normalized_faces.size == 0:
        return _empty_component_report()
    if not _is_triangular_face_array(normalized_faces):
        return _empty_component_report(invalid_face_count=malformed_row_count, malformed_face_array=True)

    valid_faces, invalid_count = _valid_faces(vertices, normalized_faces)
    if len(valid_faces) == 0:
        return _empty_component_report(invalid_face_count=invalid_count)

    parent = np.arange(len(vertices), dtype=np.int64)
    rank = np.zeros(len(vertices), dtype=np.int8)

    def find(index):
        index = int(index)
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = int(parent[index])
        return index

    def union(left, right):
        root_left = find(left)
        root_right = find(right)
        if root_left == root_right:
            return
        if rank[root_left] < rank[root_right]:
            root_left, root_right = root_right, root_left
        parent[root_right] = root_left
        if rank[root_left] == rank[root_right]:
            rank[root_left] += 1

    for a, b, c in valid_faces:
        union(a, b)
        union(b, c)

    grouped_faces = {}
    for face in valid_faces:
        grouped_faces.setdefault(find(face[0]), []).append(face)

    details = []
    for root, rows in grouped_faces.items():
        component_faces = np.asarray(rows, dtype=np.int64)
        topology = edge_usage_report(component_faces)
        signed_volume = _signed_volume(vertices, component_faces)
        details.append(
            {
                "root": int(root),
                "face_count": int(len(component_faces)),
                "signed_volume_mm3": signed_volume,
                "closed_oriented_manifold": bool(topology["closed_oriented_manifold"]),
                "boundary_edge_count": int(topology["boundary_edge_count"]),
                "non_manifold_edge_count": int(topology["non_manifold_edge_count"]),
                "inconsistent_winding_edge_count": int(topology["inconsistent_winding_edge_count"]),
            }
        )

    details.sort(key=lambda item: (-item["face_count"], item["root"]))
    component_reports = [{key: value for key, value in item.items() if key != "root"} for item in details]
    component_face_counts = [item["face_count"] for item in component_reports]
    component_volumes = [item["signed_volume_mm3"] for item in component_reports]
    component_closed = [item["closed_oriented_manifold"] for item in component_reports]
    closed_count = int(sum(component_closed))
    inward_count = int(
        sum(item["closed_oriented_manifold"] and item["signed_volume_mm3"] < 0.0 for item in component_reports)
    )
    return {
        "component_count": int(len(component_reports)),
        "component_face_counts": component_face_counts,
        "component_signed_volumes_mm3": component_volumes,
        "component_closed_oriented_flags": component_closed,
        "component_reports": component_reports,
        "largest_component_face_count": component_face_counts[0] if component_face_counts else 0,
        "closed_oriented_component_count": closed_count,
        "inward_closed_component_count": inward_count,
        "open_or_unoriented_component_count": int(len(component_reports) - closed_count),
        "valid_face_count": int(len(valid_faces)),
        "invalid_face_count": invalid_count,
        "malformed_face_array": False,
    }


def manufacturing_gate_report(vertex_count, face_count, bounds, topology, face_geometry, components, minimum_thickness_mm=None):
    """Return an explicit non-certifying gate for severe mesh defects."""
    blockers = []
    review_flags = []
    if vertex_count == 0 or face_count == 0:
        blockers.append("mesh is empty")
    if topology.get("malformed_face_array") or face_geometry.get("malformed_face_array"):
        blockers.append("face array is malformed")
    if topology["boundary_edge_count"] > 0:
        blockers.append("open boundary edges are present")
    if topology["non_manifold_edge_count"] > 0:
        blockers.append("non-manifold edges are present")
    if topology["inconsistent_winding_edge_count"] > 0:
        blockers.append("face winding is inconsistent")
    if face_geometry["invalid_face_count"] > 0:
        blockers.append("invalid face references are present")
    if face_geometry["zero_area_face_count"] > 0:
        blockers.append("zero-area faces are present")
    if components["component_count"] == 0 and face_count > 0:
        blockers.append("no valid face-connected component was found")
    if components["open_or_unoriented_component_count"] > 0:
        blockers.append("one or more components are open or unoriented")
    if components["inward_closed_component_count"] > 0:
        blockers.append("one or more closed components are oriented inward")
    if minimum_thickness_mm is not None and bounds["size_z"] < float(minimum_thickness_mm):
        blockers.append("estimated total thickness is below the configured minimum")
    if components["component_count"] > 1:
        review_flags.append("multiple disconnected components require manual review")

    return {
        "status": "blocked" if blockers else "review_required",
        "topology_checks_passed": bool(not blockers),
        "unattended_manufacturing_recommended": False,
        "blockers": blockers,
        "review_flags": review_flags,
        "missing_checks": [
            "self-intersection detection",
            "local wall-thickness analysis",
            "minimum feature-size analysis",
            "process-specific overhang and tool-access analysis",
        ],
        "disclaimer": _MANUFACTURING_DISCLAIMER,
    }


def basic_report(vertices, faces, minimum_thickness_mm=None, max_recommended_faces=200000):
    """Return a cautious advisory mesh diagnostic report."""
    vertices = _vertices_array(vertices)
    vertex_count = int(len(vertices))
    face_count = _face_row_count(faces)
    bounds = mesh_bounds(vertices)
    topology = edge_usage_report(faces)
    face_geometry = face_geometry_report(vertices, faces)
    components = connected_component_report(vertices, faces)
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
    if topology["inconsistent_winding_edge_count"] > 0:
        warnings.append("inconsistent face winding detected")
    if components["inward_closed_component_count"] > 0:
        if components["component_count"] == 1:
            warnings.append("closed mesh orientation appears inward")
        else:
            warnings.append("one or more closed mesh components appear inward")
    elif topology.get("closed_oriented_manifold") and face_geometry["signed_volume_mm3"] < 0.0:
        warnings.append("closed mesh orientation appears inward")
    if topology.get("malformed_face_array") or face_geometry.get("malformed_face_array"):
        warnings.append(_MALFORMED_FACE_WARNING)
    if face_geometry["invalid_face_count"] > 0:
        warnings.append("invalid face references detected")
    if face_geometry["zero_area_face_count"] > 0:
        warnings.append("zero-area faces detected")
    if components["component_count"] > 1:
        warnings.append("multiple disconnected mesh components detected")

    manufacturing_gate = manufacturing_gate_report(
        vertex_count,
        face_count,
        bounds,
        topology,
        face_geometry,
        components,
        minimum_thickness_mm,
    )
    return {
        "vertex_count": vertex_count,
        "face_count": face_count,
        "bbox": bounds,
        "size_mm": {"x": bounds["size_x"], "y": bounds["size_y"], "z": bounds["size_z"]},
        "estimated_total_thickness_mm": bounds["size_z"],
        "minimum_thickness_mm": minimum_thickness_mm,
        "topology": topology,
        "face_geometry": face_geometry,
        "components": components,
        "manufacturing_gate": manufacturing_gate,
        "manufacturing_advisory": _MANUFACTURING_DISCLAIMER,
        "warnings": warnings,
        "watertight_check": "oriented edge-manifold heuristic",
        "thin_region_check": "not implemented",
    }
