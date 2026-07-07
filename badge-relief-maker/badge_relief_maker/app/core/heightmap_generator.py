"""Heightmap generation from artwork."""

from __future__ import annotations

import numpy as np


def grayscale_heightmap(rgba: np.ndarray, mask: np.ndarray | None = None, invert: bool = False) -> np.ndarray:
    """Convert image luminance to a normalized heightmap in the range [0, 1]."""
    rgb = rgba[:, :, :3].astype(np.float32)
    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    if gray.max() > gray.min():
        height = (gray - gray.min()) / (gray.max() - gray.min())
    else:
        height = np.zeros_like(gray, dtype=np.float32)
    if invert:
        height = 1.0 - height
    if mask is not None:
        height = np.where(mask, height, 0.0)
    return height.astype(np.float32)


def layered_heightmap(regions: list[np.ndarray], heights: list[float], shape: tuple[int, int]) -> np.ndarray:
    """Assign fixed heights to region masks."""
    if len(regions) != len(heights):
        raise ValueError("regions and heights must have the same length")
    result = np.zeros(shape, dtype=np.float32)
    for region, height in zip(regions, heights):
        result[region.astype(bool)] = float(height)
    return np.clip(result, 0.0, 1.0)
