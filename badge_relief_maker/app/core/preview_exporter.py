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


def save_relief_preview(heightmap, mask, path, vertical_scale=8.0):
    """Save a neutral shaded preview of the relief surface.

    This is not a manufacturing render; it is a fast diagnostic view that makes
    raised detail legible before the user exports a mesh.
    """
    path = Path(path)
    height = np.asarray(heightmap, dtype=np.float32)
    foreground = np.asarray(mask, dtype=bool)
    if foreground.shape != height.shape:
        raise ValueError("mask and heightmap must have the same shape")

    gradient_y = np.gradient(height, axis=0) if height.shape[0] > 1 else np.zeros_like(height)
    gradient_x = np.gradient(height, axis=1) if height.shape[1] > 1 else np.zeros_like(height)
    normal_x = -gradient_x * float(vertical_scale)
    normal_y = -gradient_y * float(vertical_scale)
    normal_z = np.ones_like(height)
    norm = np.sqrt(normal_x * normal_x + normal_y * normal_y + normal_z * normal_z)
    normal_x /= np.maximum(norm, 1e-8)
    normal_y /= np.maximum(norm, 1e-8)
    normal_z /= np.maximum(norm, 1e-8)

    light = np.asarray([-0.45, -0.50, 0.74], dtype=np.float32)
    light /= np.linalg.norm(light)
    diffuse = np.clip(normal_x * light[0] + normal_y * light[1] + normal_z * light[2], 0.0, 1.0)
    shade = 0.22 + 0.78 * diffuse
    surface = np.stack(
        [shade * 0.82 + 0.10 * height, shade * 0.85 + 0.11 * height, shade * 0.90 + 0.12 * height], axis=2
    )
    background = np.full_like(surface, 0.12)
    result = np.where(foreground[:, :, None], surface, background)
    Image.fromarray(np.clip(result * 255.0, 0, 255).astype(np.uint8), mode="RGB").save(path)
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
