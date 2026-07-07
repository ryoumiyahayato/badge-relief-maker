"""Heightmap generation from artwork."""

import numpy as np


def empty_heightmap(shape):
    """Create an empty heightmap for tests and early wiring."""
    return np.zeros(shape, dtype=np.float32)


def grayscale_heightmap(rgba, mask=None, invert=False):
    """Convert image brightness to a normalized heightmap."""
    rgb = rgba[:, :, :3].astype(np.float32)
    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    low = float(gray.min())
    high = float(gray.max())
    if high > low:
        result = (gray - low) / (high - low)
    else:
        result = np.zeros_like(gray, dtype=np.float32)
    if invert:
        result = 1.0 - result
    if mask is not None:
        result = np.where(mask, result, 0.0)
    return result.astype(np.float32)


def layered_heightmap(regions, heights, shape):
    """Assign fixed heights to region masks."""
    result = np.zeros(shape, dtype=np.float32)
    for region, height in zip(regions, heights):
        result[region.astype(bool)] = float(height)
    return result
