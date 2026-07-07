"""Image loading and preprocessing helpers."""

from pathlib import Path

import numpy as np
from PIL import Image


def load_rgba(path: str | Path) -> np.ndarray:
    """Load an image as RGBA pixels."""
    return np.asarray(Image.open(path).convert("RGBA"))


def normalize_alpha_background(image: np.ndarray, threshold: int = 5) -> np.ndarray:
    """Set near transparent alpha values to zero."""
    result = image.copy()
    alpha = result[:, :, 3]
    alpha[alpha <= threshold] = 0
    result[:, :, 3] = alpha
    return result
