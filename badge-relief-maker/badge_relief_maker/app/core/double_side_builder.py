"""Front/back relief combination helpers."""

from __future__ import annotations

import numpy as np


def align_placeholder(front_heightmap: np.ndarray, back_heightmap: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Placeholder for front/back alignment.

    The MVP should add manual scale, rotation and XY offset controls before
    attempting automatic alignment.
    """
    if front_heightmap.shape != back_heightmap.shape:
        raise ValueError("Front and back heightmaps must have the same shape in this placeholder")
    return front_heightmap, back_heightmap
