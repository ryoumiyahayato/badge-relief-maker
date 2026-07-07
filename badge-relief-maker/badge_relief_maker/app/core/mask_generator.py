"""Foreground mask generation."""

from __future__ import annotations

import numpy as np


def alpha_mask(rgba: np.ndarray, threshold: int = 1) -> np.ndarray:
    """Create a boolean mask from an RGBA image alpha channel."""
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("Expected RGBA image with shape (h, w, 4)")
    return rgba[:, :, 3] >= threshold


def luminance_mask(rgba: np.ndarray, threshold: int = 20) -> np.ndarray:
    """Create a foreground mask from luminance for images without alpha."""
    rgb = rgba[:, :, :3].astype(np.float32)
    luminance = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    return luminance >= threshold
