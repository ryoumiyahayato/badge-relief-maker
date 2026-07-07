"""Preview image export helpers."""

from pathlib import Path

import numpy as np
from PIL import Image


def save_mask_preview(mask, path):
    """Save a black and white mask preview image."""
    path = Path(path)
    data = np.where(mask, 255, 0).astype(np.uint8)
    Image.fromarray(data, mode="L").save(path)
    return str(path)


def save_heightmap_preview(heightmap, path):
    """Save a grayscale heightmap preview image."""
    path = Path(path)
    values = heightmap.astype(float)
    if values.size and values.max() > values.min():
        values = (values - values.min()) / (values.max() - values.min())
    data = np.clip(values * 255.0, 0, 255).astype(np.uint8)
    Image.fromarray(data, mode="L").save(path)
    return str(path)
