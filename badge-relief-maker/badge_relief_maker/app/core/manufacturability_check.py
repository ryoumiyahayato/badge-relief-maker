"""Basic manufacturability report helpers."""

from __future__ import annotations

import numpy as np


def basic_report(vertices: np.ndarray, faces: np.ndarray, minimum_thickness_mm: float | None = None) -> dict[str, object]:
    """Return a simple mesh diagnostic report.

    Future work should add watertightness, non-manifold edges, thin region checks
    and normal direction repair.
    """
    report: dict[str, object] = {
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        "minimum_thickness_mm": minimum_thickness_mm,
        "watertight_check": "not implemented",
        "thin_region_check": "not implemented",
    }
    return report
