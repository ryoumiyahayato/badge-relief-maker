"""Heightmap generation from artwork."""

import numpy as np


def empty_heightmap(shape):
    """Create an empty heightmap for tests and early wiring."""
    return np.zeros(shape, dtype=np.float32)


def grayscale_heightmap(rgba, mask=None, invert=False):
    """Convert image brightness to a normalized foreground heightmap.

    Foreground normalization ignores background pixels. A uniformly bright
    foreground has no recoverable relative depth, so the deterministic default is
    a constant full-height value of 1.0 before optional inversion. This produces a
    usable raised plateau while still satisfying ``inverted = 1 - normal``.
    """
    rgba = np.asarray(rgba)
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("expected rgba image")
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
            normalized = np.ones_like(gray, dtype=np.float32)
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
