"""Outer rim helpers for badge-like relief generation."""

import numpy as np


def boundary_cell_mask(mask):
    """Return foreground cells that touch the exterior of the mask."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")
    rows, cols = mask.shape
    boundary = np.zeros_like(mask, dtype=bool)
    for r in range(rows):
        for c in range(cols):
            if not bool(mask[r, c]):
                continue
            if (
                r == 0
                or c == 0
                or r == rows - 1
                or c == cols - 1
                or not bool(mask[r - 1, c])
                or not bool(mask[r + 1, c])
                or not bool(mask[r, c - 1])
                or not bool(mask[r, c + 1])
            ):
                boundary[r, c] = True
    return boundary


def inner_rim_mask(mask, width_px=1):
    """Return foreground cells within width_px steps from the exterior boundary."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")
    width = int(width_px)
    if width <= 0 or not mask.any():
        return np.zeros_like(mask, dtype=bool)

    rim = boundary_cell_mask(mask)
    frontier = rim.copy()
    for _ in range(1, width):
        expanded = _expand_one_step(frontier) & mask & ~rim
        if not expanded.any():
            break
        rim |= expanded
        frontier = expanded
    return rim


def apply_outer_rim_to_heightmap(heightmap, mask, width_px=0, rim_height_mm=0.0, relief_height_mm=1.0):
    """Raise foreground boundary cells in the heightmap to create a simple rim.

    The heightmap remains normalized. The requested rim height is converted into
    normalized units by dividing by relief_height_mm, then added to rim cells and
    clipped to 1.0 for this MVP path.
    """
    heightmap = np.asarray(heightmap, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if heightmap.shape != mask.shape:
        raise ValueError("heightmap and mask must have the same shape")
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")

    width = int(width_px)
    height_mm = float(rim_height_mm)
    relief_mm = float(relief_height_mm)
    report = {
        "enabled": False,
        "rim_width_px": max(0, width),
        "rim_height_mm": height_mm,
        "rim_pixel_count": 0,
        "boost_normalized": 0.0,
        "clipped_pixel_count": 0,
    }
    if width <= 0 or height_mm <= 0.0 or relief_mm <= 0.0 or not mask.any():
        return heightmap.copy(), report

    rim = inner_rim_mask(mask, width)
    boost = height_mm / relief_mm
    result = heightmap.copy()
    before = result[rim]
    after_unclipped = before + boost
    result[rim] = np.clip(after_unclipped, 0.0, 1.0)
    report.update(
        {
            "enabled": True,
            "rim_pixel_count": int(rim.sum()),
            "boost_normalized": float(boost),
            "clipped_pixel_count": int(np.count_nonzero(after_unclipped > 1.0)),
        }
    )
    return result, report


def _expand_one_step(mask):
    expanded = np.zeros_like(mask, dtype=bool)
    expanded[:-1, :] |= mask[1:, :]
    expanded[1:, :] |= mask[:-1, :]
    expanded[:, :-1] |= mask[:, 1:]
    expanded[:, 1:] |= mask[:, :-1]
    return expanded
