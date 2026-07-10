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


def save_source_preview(rgba, path):
    """Save the processed RGBA source used by the final geometry grid."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(rgba, dtype=np.uint8), mode="RGBA").save(path)
    return str(path)


def save_mask_overlay_preview(rgba, mask, path):
    """Save an exact final-grid source/mask overlay."""
    source = np.asarray(rgba, dtype=np.uint8)
    foreground = np.asarray(mask, dtype=bool)
    if source.shape[:2] != foreground.shape:
        raise ValueError("source preview and mask must have the same shape")
    overlay = source.copy().astype(np.float32)
    tint = np.asarray([255.0, 55.0, 55.0], dtype=np.float32)
    overlay[foreground, :3] = overlay[foreground, :3] * 0.55 + tint * 0.45
    overlay[~foreground, :3] *= 0.25
    overlay[:, :, 3] = 255
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8), mode="RGBA").save(path)
    return str(path)
