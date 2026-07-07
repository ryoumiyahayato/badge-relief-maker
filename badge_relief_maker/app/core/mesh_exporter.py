"""Mesh export helpers."""

from pathlib import Path

import numpy as np


def export_obj(path, vertices, faces):
    """Export a minimal OBJ file."""
    path = Path(path)
    with path.open("w", encoding="utf-8") as fh:
        for x, y, z in vertices:
            fh.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            fh.write(f"f {a + 1} {b + 1} {c + 1}\n")


def _facet_normal(a, b, c):
    """Compute a normalized triangle normal."""
    ab = b - a
    ac = c - a
    normal = np.cross(ab, ac)
    length = float(np.linalg.norm(normal))
    if length == 0.0:
        return np.asarray([0.0, 0.0, 0.0], dtype=float)
    return normal / length


def export_ascii_stl(path, vertices, faces, solid_name="badge_relief"):
    """Export a minimal ASCII STL file.

    ASCII STL is larger than binary STL but easy to inspect and sufficient for
    the first local MVP. A binary STL exporter can be added later.
    """
    path = Path(path)
    verts = np.asarray(vertices, dtype=float)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f"solid {solid_name}\n")
        for face in faces:
            a, b, c = verts[face[0]], verts[face[1]], verts[face[2]]
            n = _facet_normal(a, b, c)
            fh.write(f"  facet normal {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")
            fh.write("    outer loop\n")
            fh.write(f"      vertex {a[0]:.6f} {a[1]:.6f} {a[2]:.6f}\n")
            fh.write(f"      vertex {b[0]:.6f} {b[1]:.6f} {b[2]:.6f}\n")
            fh.write(f"      vertex {c[0]:.6f} {c[1]:.6f} {c[2]:.6f}\n")
            fh.write("    endloop\n")
            fh.write("  endfacet\n")
        fh.write(f"endsolid {solid_name}\n")


def export_mesh(path, vertices, faces):
    """Export mesh by file extension."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".obj":
        export_obj(path, vertices, faces)
    elif suffix == ".stl":
        export_ascii_stl(path, vertices, faces)
    else:
        raise ValueError(f"unsupported export format: {suffix}")


def supported_formats():
    """Return planned export formats."""
    return {"stl", "obj", "glb"}


def implemented_formats():
    """Return currently implemented export formats."""
    return {"obj", "stl"}
