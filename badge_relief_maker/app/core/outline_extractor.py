"""Mask outline extraction helpers.

These functions do not yet build a smoothed contour mesh. They extract the grid
boundary of a foreground mask so the pipeline can report outline complexity and
later replace pixel-cell side closure with contour-based side closure.
"""

import numpy as np


def boundary_edges_from_mask(mask):
    """Return foreground boundary edges in grid coordinates.

    Each edge is represented as ((x0, y0), (x1, y1)) where coordinates are in
    mask grid units, not millimeters.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")

    rows, cols = mask.shape
    edges = []
    for r in range(rows):
        for c in range(cols):
            if not bool(mask[r, c]):
                continue
            x0 = c
            x1 = c + 1
            y0 = r
            y1 = r + 1

            if r == 0 or not bool(mask[r - 1, c]):
                edges.append(((x0, y0), (x1, y0)))
            if c == cols - 1 or not bool(mask[r, c + 1]):
                edges.append(((x1, y0), (x1, y1)))
            if r == rows - 1 or not bool(mask[r + 1, c]):
                edges.append(((x1, y1), (x0, y1)))
            if c == 0 or not bool(mask[r, c - 1]):
                edges.append(((x0, y1), (x0, y0)))
    return edges


def outline_report(mask, width_mm, height_mm):
    """Return lightweight outline metrics for a mask footprint."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")
    rows, cols = mask.shape
    if rows <= 0 or cols <= 0:
        raise ValueError("mask must be non-empty")

    edges = boundary_edges_from_mask(mask)
    cell_w = float(width_mm) / float(cols)
    cell_h = float(height_mm) / float(rows)
    horizontal_count = 0
    vertical_count = 0
    for (x0, y0), (x1, y1) in edges:
        if y0 == y1:
            horizontal_count += 1
        elif x0 == x1:
            vertical_count += 1

    foreground_pixels = int(mask.sum())
    grid_pixels = int(mask.size)
    fill_ratio = float(foreground_pixels) / float(grid_pixels) if grid_pixels else 0.0
    bbox = _mask_bbox(mask)
    outline_guess = _guess_outline_type(mask, bbox, fill_ratio)

    return {
        "boundary_edge_count": int(len(edges)),
        "horizontal_boundary_edge_count": int(horizontal_count),
        "vertical_boundary_edge_count": int(vertical_count),
        "boundary_length_mm": float(horizontal_count * cell_w + vertical_count * cell_h),
        "foreground_pixel_count": foreground_pixels,
        "fill_ratio": fill_ratio,
        "grid_shape": tuple(mask.shape),
        "bbox": bbox,
        "outline_guess": outline_guess,
    }


def _mask_bbox(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _guess_outline_type(mask, bbox, fill_ratio):
    """Return a very rough outline type guess for UI labeling."""
    if bbox is None:
        return "empty"
    x0, y0, x1, y1 = bbox
    bbox_width = max(1, x1 - x0)
    bbox_height = max(1, y1 - y0)
    aspect = float(bbox_width) / float(bbox_height)
    local_fill = float(mask[y0:y1, x0:x1].sum()) / float(bbox_width * bbox_height)

    if local_fill > 0.90:
        return "rectangle_or_solid_plate"
    if 0.65 <= local_fill <= 0.86:
        if 0.85 <= aspect <= 1.15:
            return "circle_like"
        return "ellipse_like"
    if fill_ratio < 0.05:
        return "small_or_fragmented"
    return "custom"
