"""Mesh repair placeholder utilities."""

from __future__ import annotations

import numpy as np


def face_count(faces: np.ndarray) -> int:
    """Return the number of mesh faces."""
    return int(len(faces))


def remove_duplicate_vertices(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Placeholder for vertex cleanup.

    A real implementation should preserve face references after deduplication.
    For now this returns the input unchanged.
    """
    return vertices, faces
