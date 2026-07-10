"""Independent export read-back validation using trimesh."""

from pathlib import Path

import numpy as np
import trimesh


def validate_export(path, expected_size_mm=None, tolerance_mm=0.05):
    """Load OBJ/STL/GLB independently and report geometry acceptance facts."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"export does not exist: {path}")
    # Processing welds STL's deliberately duplicated per-facet vertices while
    # preserving geometry, enabling the same topology checks across formats.
    loaded = trimesh.load(path, force="scene", process=True)
    if isinstance(loaded, trimesh.Trimesh):
        geometries = [loaded]
    else:
        geometries = [geometry for geometry in loaded.geometry.values() if isinstance(geometry, trimesh.Trimesh)]
    if not geometries:
        raise ValueError(f"export contains no mesh geometry: {path}")
    combined = trimesh.util.concatenate(geometries)
    bounds = np.asarray(combined.bounds, dtype=float)
    size = bounds[1] - bounds[0]
    dimension_errors = None
    dimensions_match = None
    if expected_size_mm is not None:
        expected = np.asarray(expected_size_mm, dtype=float)
        if expected.shape != (3,):
            raise ValueError("expected_size_mm must contain X, Y and Z")
        dimension_errors = np.abs(size - expected)
        dimensions_match = bool(np.all(dimension_errors <= float(tolerance_mm)))
    return {
        "path": str(path),
        "format": path.suffix.lower().lstrip("."),
        "geometry_count": len(geometries),
        "vertex_count": int(sum(len(mesh.vertices) for mesh in geometries)),
        "face_count": int(sum(len(mesh.faces) for mesh in geometries)),
        "size_mm": size.astype(float).tolist(),
        "watertight": bool(all(mesh.is_watertight for mesh in geometries)),
        "winding_consistent": bool(all(mesh.is_winding_consistent for mesh in geometries)),
        "positive_volume": bool(all(float(mesh.volume) > 0.0 for mesh in geometries)),
        "dimension_error_mm": dimension_errors.astype(float).tolist() if dimension_errors is not None else None,
        "dimensions_match": dimensions_match,
        "loader": f"trimesh {trimesh.__version__}",
    }
