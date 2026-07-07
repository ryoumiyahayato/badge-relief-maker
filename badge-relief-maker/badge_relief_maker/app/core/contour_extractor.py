"""Contour and connected-region extraction."""

from __future__ import annotations

import numpy as np


def bounding_box(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return x_min, y_min, x_max, y_max for a boolean mask."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def placeholder_regions(mask: np.ndarray) -> list[np.ndarray]:
    """Return a single region for now.

    Future implementation should use connected components, watershed or manual
    region painting for layer-based relief editing.
    """
    return [mask.astype(bool)] if mask.any() else []
