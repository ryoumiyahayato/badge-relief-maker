"""Heightmap generation from artwork."""

import numpy as np


def empty_heightmap(shape):
    """Create an empty heightmap for tests and early wiring."""
    return np.zeros(shape, dtype=np.float32)


def grayscale_heightmap(rgba, mask=None, invert=False):
    """Convert image brightness to a normalized heightmap.

    When a mask is provided, normalization uses only foreground pixels so hidden
    or transparent background RGB values cannot change the relief range.
    """
    rgb = rgba[:, :, :3].astype(np.float32)
    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]

    if mask is None:
        sample = gray.reshape(-1)
        foreground = None
    else:
        foreground = np.asarray(mask, dtype=bool)
        if foreground.shape != gray.shape:
            raise ValueError("mask and image must have the same height and width")
        sample = gray[foreground]

    result = np.zeros_like(gray, dtype=np.float32)
    if sample.size:
        low = float(sample.min())
        high = float(sample.max())
        if high > low:
            normalized = (gray - low) / (high - low)
        else:
            normalized = np.zeros_like(gray, dtype=np.float32)
        if invert:
            normalized = 1.0 - normalized
        result = normalized.astype(np.float32)

    if foreground is not None:
        result = np.where(foreground, result, 0.0)
    return result.astype(np.float32)


def layered_heightmap(regions, heights, shape):
    """Assign fixed heights to region masks."""
    result = np.zeros(shape, dtype=np.float32)
    for region, height in zip(regions, heights):
        result[region.astype(bool)] = float(height)
    return result
