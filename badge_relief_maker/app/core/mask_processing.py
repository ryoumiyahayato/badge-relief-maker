"""Mask and heightmap processing helpers."""

import math

import numpy as np
from PIL import Image

from .components import connected_components


def mask_bbox(mask, padding=0):
    """Return a padded bounding box as x0, y0, x1, y1."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    height, width = mask.shape
    x0 = max(int(xs.min()) - int(padding), 0)
    y0 = max(int(ys.min()) - int(padding), 0)
    x1 = min(int(xs.max()) + int(padding) + 1, width)
    y1 = min(int(ys.max()) + int(padding) + 1, height)
    return x0, y0, x1, y1


def remove_small_components(mask, min_pixels=1):
    """Remove foreground islands smaller than min_pixels."""
    if min_pixels is None or int(min_pixels) <= 1:
        return mask.astype(bool), 0
    result = mask.astype(bool).copy()
    removed = 0
    for component in connected_components(result):
        if len(component.pixels) < int(min_pixels):
            removed += len(component.pixels)
            for y, x in component.pixels:
                result[y, x] = False
    return result, removed


def fill_small_holes(mask, max_pixels=0):
    """Fill background holes smaller than max_pixels that do not touch border."""
    if max_pixels is None or int(max_pixels) <= 0:
        return mask.astype(bool), 0
    result = mask.astype(bool).copy()
    filled = 0
    for component in connected_components(result, target=False):
        if not component.touches_border and len(component.pixels) <= int(max_pixels):
            filled += len(component.pixels)
            for y, x in component.pixels:
                result[y, x] = True
    return result, filled


def majority_smooth_mask(mask, iterations=0):
    """Apply a small 3x3 majority filter to reduce single-pixel jagged noise."""
    result = mask.astype(bool).copy()
    for _ in range(max(0, int(iterations))):
        padded = np.pad(result, 1, mode="edge")
        score = np.zeros_like(result, dtype=np.int16)
        for dy in range(3):
            for dx in range(3):
                score += padded[dy : dy + result.shape[0], dx : dx + result.shape[1]]
        result = score >= 5
    return result


def clean_mask(mask, min_component_pixels=1, fill_hole_pixels=0, smooth_iterations=0):
    """Run conservative local mask cleanup and return metadata."""
    cleaned, removed_pixels = remove_small_components(mask, min_component_pixels)
    cleaned, filled_pixels = fill_small_holes(cleaned, fill_hole_pixels)
    cleaned = majority_smooth_mask(cleaned, smooth_iterations)
    return cleaned, {
        "removed_small_component_pixels": int(removed_pixels),
        "filled_hole_pixels": int(filled_pixels),
        "smooth_iterations": int(max(0, smooth_iterations)),
    }


def crop_to_mask(mask, heightmap, padding=1):
    """Crop mask and heightmap to the foreground bounding box."""
    box = mask_bbox(mask, padding=padding)
    if box is None:
        return mask, heightmap, None
    x0, y0, x1, y1 = box
    return mask[y0:y1, x0:x1], heightmap[y0:y1, x0:x1], box


def resize_mask_and_heightmap(mask, heightmap, max_cells):
    """Downsample mask and heightmap when the grid is too large."""
    if max_cells is None or max_cells <= 0:
        return mask, heightmap, 1.0

    rows, cols = mask.shape
    current = rows * cols
    if current <= max_cells:
        return mask, heightmap, 1.0

    scale = math.sqrt(float(max_cells) / float(current))
    new_cols = max(2, int(cols * scale))
    new_rows = max(2, int(rows * scale))

    mask_img = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    height_img = Image.fromarray(np.clip(heightmap * 255.0, 0, 255).astype(np.uint8), mode="L")

    resized_mask = np.asarray(mask_img.resize((new_cols, new_rows), Image.Resampling.NEAREST)) > 0
    resized_height = np.asarray(height_img.resize((new_cols, new_rows), Image.Resampling.BILINEAR)).astype(np.float32) / 255.0
    resized_height = np.where(resized_mask, resized_height, 0.0).astype(np.float32)
    return resized_mask, resized_height, scale
