"""Heightmap generation from artwork."""

import numpy as np


def empty_heightmap(shape):
    """Create an empty heightmap for tests and early wiring."""
    return np.zeros(shape, dtype=np.float32)


def layered_heightmap(regions, heights, shape):
    """Assign fixed heights to region masks."""
    result = np.zeros(shape, dtype=np.float32)
    for region, height in zip(regions, heights):
        result[region.astype(bool)] = float(height)
    return result
