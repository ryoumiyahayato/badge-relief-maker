"""Contour and region extraction placeholders."""

import numpy as np


def bounding_box(mask):
    """Return a simple box for a mask."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def placeholder_regions(mask):
    """Return one region for the current scaffold."""
    return [mask.astype(bool)] if mask.any() else []
