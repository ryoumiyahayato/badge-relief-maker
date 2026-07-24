"""Preview image export helpers."""

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def save_mask_preview(mask, path):
    """Save a black and white mask preview image."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.where(mask, 255, 0).astype(np.uint8)
    Image.fromarray(data, mode="L").save(path)
    return str(path)


def save_heightmap_preview(heightmap, path):
    """Save a grayscale heightmap preview image."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    values = heightmap.astype(float)
    if values.size and values.max() > values.min():
        values = (values - values.min()) / (values.max() - values.min())
    data = np.clip(values * 255.0, 0, 255).astype(np.uint8)
    Image.fromarray(data, mode="L").save(path)
    return str(path)


def save_relief_preview(heightmap, mask, path, vertical_scale=16.0):
    """Save a studio-style render computed from the real final height field.

    The image is not an invented effect layer. Surface normals, key/fill lighting,
    cavity darkening, specular response and the cast silhouette shadow are all
    derived from the same heightmap and footprint used to build the exported mesh.
    This makes broad high/low form visible before export instead of showing what is
    effectively only an edge map.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    height = np.asarray(heightmap, dtype=np.float32)
    foreground = np.asarray(mask, dtype=bool)
    if foreground.shape != height.shape:
        raise ValueError("mask and heightmap must have the same shape")

    if height.size == 0:
        Image.new("RGB", (1, 1), (236, 236, 234)).save(path)
        return str(path)

    smooth = ndi.gaussian_filter(height, sigma=0.65)
    gradient_y = np.gradient(smooth, axis=0) if smooth.shape[0] > 1 else np.zeros_like(smooth)
    gradient_x = np.gradient(smooth, axis=1) if smooth.shape[1] > 1 else np.zeros_like(smooth)
    normal_x = -gradient_x * float(vertical_scale)
    normal_y = -gradient_y * float(vertical_scale)
    normal_z = np.ones_like(height)
    norm = np.sqrt(normal_x * normal_x + normal_y * normal_y + normal_z * normal_z)
    normal_x /= np.maximum(norm, 1e-8)
    normal_y /= np.maximum(norm, 1e-8)
    normal_z /= np.maximum(norm, 1e-8)

    key = np.asarray([-0.45, -0.55, 0.70], dtype=np.float32)
    key /= np.linalg.norm(key)
    fill = np.asarray([0.60, 0.15, 0.78], dtype=np.float32)
    fill /= np.linalg.norm(fill)
    view = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
    half_vector = key + view
    half_vector /= np.linalg.norm(half_vector)

    diffuse = np.clip(normal_x * key[0] + normal_y * key[1] + normal_z * key[2], 0.0, 1.0)
    fill_light = np.clip(normal_x * fill[0] + normal_y * fill[1] + normal_z * fill[2], 0.0, 1.0)
    specular = np.clip(
        normal_x * half_vector[0] + normal_y * half_vector[1] + normal_z * half_vector[2],
        0.0,
        1.0,
    ) ** 26

    local_mean = ndi.gaussian_filter(smooth, sigma=4.0)
    cavity = np.clip((local_mean - smooth) * 3.0, 0.0, 0.35)
    shade = np.clip(0.18 + 0.72 * diffuse + 0.18 * fill_light - cavity, 0.0, 1.4)

    bronze = np.asarray([0.52, 0.24, 0.075], dtype=np.float32)
    highlight = np.asarray([0.55, 0.40, 0.25], dtype=np.float32)
    surface = bronze[None, None, :] * shade[:, :, None]
    surface += specular[:, :, None] * highlight[None, None, :]
    surface += smooth[:, :, None] * 0.05

    rows, cols = height.shape
    vertical_gradient = np.linspace(0.0, 1.0, rows, dtype=np.float32)[:, None]
    background_value = 0.88 + 0.07 * (1.0 - vertical_gradient)
    background = np.repeat(background_value[:, :, None], cols, axis=1)
    background = np.repeat(background, 3, axis=2)

    shadow = np.zeros_like(height, dtype=np.float32)
    offset_y = max(3, rows // 60)
    offset_x = max(3, cols // 60)
    if rows > offset_y and cols > offset_x:
        shadow[offset_y:, offset_x:] = foreground[:-offset_y, :-offset_x]
    shadow = ndi.gaussian_filter(shadow, sigma=max(2.0, min(rows, cols) / 100.0))
    background *= 1.0 - 0.22 * shadow[:, :, None]

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
