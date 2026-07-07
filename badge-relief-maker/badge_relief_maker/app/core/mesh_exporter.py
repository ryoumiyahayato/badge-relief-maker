"""Mesh export helpers."""

from __future__ import annotations

from pathlib import Path
import numpy as np


def export_obj(path: str | Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    """Export a minimal OBJ file.

    This keeps the scaffold usable before trimesh export integration is added.
    """
    path = Path(path)
    with path.open("w", encoding="utf-8") as fh:
        for x, y, z in vertices:
            fh.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            fh.write(f"f {a + 1} {b + 1} {c + 1}\n")


def supported_formats() -> set[str]:
    """Return planned export formats."""
    return {"stl", "obj", "glb"}
