"""Image loading and preprocessing helpers."""

from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image


def load_rgba(path: str | Path) -> np.ndarray:
    """Load an image as an RGBA NumPy array."""
    return np.asarray(Image.open(path).convert("RGBA"))


def normalize_alpha_background(image: np.ndarray, background_threshold: int = 5) -> np.ndarray:
    """Return a copy where near-transparent alpha values are set to zero.

    This is intentionally conservative. More advanced background removal should
    be added later as an optional step.
    """
    result = image.copy()
    alpha = result[:, :, 3]
    alpha[alpha <= background_threshold] = 0
    result[:, :, 3] = alpha
    return result
