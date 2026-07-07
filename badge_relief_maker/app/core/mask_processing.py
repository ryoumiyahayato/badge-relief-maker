"""Mask and heightmap processing helpers."""

import math

import numpy as np
from PIL import Image


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
