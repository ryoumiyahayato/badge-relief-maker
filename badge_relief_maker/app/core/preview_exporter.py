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


def _masked_gaussian(values, mask, sigma):
    weights = np.asarray(mask, dtype=bool).astype(np.float32)
    numerator = ndi.gaussian_filter(np.asarray(values, dtype=np.float32) * weights, sigma=float(sigma), mode="constant")
    denominator = ndi.gaussian_filter(weights, sigma=float(sigma), mode="constant")
    return np.divide(numerator, denominator, out=np.asarray(values, dtype=np.float32).copy(), where=denominator > 1e-8)


def save_relief_preview(
    heightmap,
    mask,
    path,
    vertical_scale=10.0,
    *,
    width_mm=None,
    height_mm=None,
    relief_height_mm=None,
    display_exaggeration=1.65,
    render_scale=2.0,
):
    """Save a smooth studio render computed from the real final height field.

    Macro form and engraving detail are shaded at different scales. This prevents
    dense historical hatching from dominating the preview while preserving the
    same final geometry: no extra ridges or decorative forms are painted into the
    image. When physical dimensions are supplied, normals are derived from true
    millimetre slopes and only the documented display exaggeration is applied.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    height = np.asarray(heightmap, dtype=np.float32)
    foreground = np.asarray(mask, dtype=bool)
    if foreground.shape != height.shape:
        raise ValueError("mask and heightmap must have the same shape")

    if height.size == 0:
        Image.new("RGB", (1, 1), (238, 238, 236)).save(path)
        return str(path)

    scale = max(float(render_scale), 1.0)
    if scale > 1.0:
        height = ndi.zoom(height, zoom=scale, order=3, mode="nearest", prefilter=True).astype(np.float32)
        alpha = np.clip(ndi.zoom(foreground.astype(np.float32), zoom=scale, order=1, mode="nearest"), 0.0, 1.0)
        foreground = alpha >= 0.50
    else:
        alpha = foreground.astype(np.float32)

    macro = _masked_gaussian(height, foreground, sigma=1.55 * scale)
    low_frequency = _masked_gaussian(height, foreground, sigma=4.8 * scale)
    micro = height - low_frequency
    render_height = np.where(foreground, np.clip(macro + 0.10 * micro, 0.0, 1.0), 0.0)

    gradient_y = np.gradient(render_height, axis=0) if render_height.shape[0] > 1 else np.zeros_like(render_height)
    gradient_x = np.gradient(render_height, axis=1) if render_height.shape[1] > 1 else np.zeros_like(render_height)

    rows, cols = height.shape
    if width_mm and height_mm and relief_height_mm:
        cell_x = float(width_mm) / float(max(cols - 1, 1))
        cell_y = float(height_mm) / float(max(rows - 1, 1))
        scale_x = float(relief_height_mm) / max(cell_x, 1e-8) * float(display_exaggeration)
        scale_y = float(relief_height_mm) / max(cell_y, 1e-8) * float(display_exaggeration)
    else:
        scale_x = scale_y = float(vertical_scale)

    normal_x = -gradient_x * scale_x
    normal_y = -gradient_y * scale_y
    normal_z = np.ones_like(height)
    norm = np.sqrt(normal_x * normal_x + normal_y * normal_y + normal_z * normal_z)
    normal_x /= np.maximum(norm, 1e-8)
    normal_y /= np.maximum(norm, 1e-8)
    normal_z /= np.maximum(norm, 1e-8)

    key = np.asarray([-0.42, -0.50, 0.76], dtype=np.float32)
    key /= np.linalg.norm(key)
    fill = np.asarray([0.55, 0.18, 0.82], dtype=np.float32)
    fill /= np.linalg.norm(fill)
    rim = np.asarray([-0.30, 0.72, 0.63], dtype=np.float32)
    rim /= np.linalg.norm(rim)
    view = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
    half_vector = key + view
    half_vector /= np.linalg.norm(half_vector)

    diffuse = np.clip(normal_x * key[0] + normal_y * key[1] + normal_z * key[2], 0.0, 1.0)
    fill_light = np.clip(normal_x * fill[0] + normal_y * fill[1] + normal_z * fill[2], 0.0, 1.0)
    rim_light = np.clip(normal_x * rim[0] + normal_y * rim[1] + normal_z * rim[2], 0.0, 1.0)
    specular = np.clip(
        normal_x * half_vector[0] + normal_y * half_vector[1] + normal_z * half_vector[2],
        0.0,
        1.0,
    ) ** 34

    cavity_reference = _masked_gaussian(render_height, foreground, sigma=5.0 * scale)
    cavity = np.clip((cavity_reference - render_height) * 1.35, 0.0, 0.16)
    shade = np.clip(0.31 + 0.61 * diffuse + 0.17 * fill_light + 0.09 * rim_light - cavity, 0.0, 1.35)

    bronze = np.asarray([0.58, 0.29, 0.105], dtype=np.float32)
    highlight = np.asarray([0.72, 0.54, 0.31], dtype=np.float32)
    surface = bronze[None, None, :] * shade[:, :, None]
    surface += specular[:, :, None] * highlight[None, None, :]
    surface += render_height[:, :, None] * 0.035

    vertical_gradient = np.linspace(0.0, 1.0, rows, dtype=np.float32)[:, None]
    background_value = 0.90 + 0.055 * (1.0 - vertical_gradient)
    background = np.repeat(background_value[:, :, None], cols, axis=1)
    background = np.repeat(background, 3, axis=2)

    shadow = np.zeros_like(height, dtype=np.float32)
    offset_y = max(3, rows // 70)
    offset_x = max(3, cols // 70)
    if rows > offset_y and cols > offset_x:
        shadow[offset_y:, offset_x:] = foreground[:-offset_y, :-offset_x]
    shadow = ndi.gaussian_filter(shadow, sigma=max(2.0, min(rows, cols) / 115.0))
    background *= 1.0 - 0.18 * shadow[:, :, None]

    result = surface * alpha[:, :, None] + background * (1.0 - alpha[:, :, None])
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
