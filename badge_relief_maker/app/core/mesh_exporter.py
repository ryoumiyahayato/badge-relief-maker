"""Mesh export helpers."""

from pathlib import Path


def export_obj(path, vertices, faces):
    """Export a minimal OBJ file."""
    path = Path(path)
    with path.open("w", encoding="utf-8") as fh:
        for x, y, z in vertices:
            fh.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            fh.write(f"f {a + 1} {b + 1} {c + 1}\n")


def supported_formats():
    """Return planned export formats."""
    return {"stl", "obj", "glb"}
