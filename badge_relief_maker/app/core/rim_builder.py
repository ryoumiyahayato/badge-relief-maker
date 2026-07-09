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


def rim_distance_map(mask, width_px=1):
    """Return inward distance from exterior boundary for rim cells.

    Boundary cells have distance 0. Cells outside the requested rim width are -1.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")
    width = int(width_px)
    distances = np.full(mask.shape, -1, dtype=np.int64)
    if width <= 0 or not mask.any():
        return distances

    frontier = boundary_cell_mask(mask)
    distances[frontier] = 0
    for distance in range(1, width):
        expanded = _expand_one_step(frontier) & mask & (distances < 0)
        if not expanded.any():
            break
        distances[expanded] = distance
        frontier = expanded
    return distances


def inner_rim_mask(mask, width_px=1):
    """Return foreground cells within width_px steps from the exterior boundary."""
    return rim_distance_map(mask, width_px) >= 0


def rim_boost_map(mask, width_px=1, boost_normalized=0.0, profile="flat"):
    """Return a normalized boost map for the requested rim profile.

    Supported profiles:
    - flat: every rim cell receives the same boost.
    - linear: boost tapers inward in a straight ramp.
    - smooth: boost uses a smoothstep ramp for a softer rounded-looking rim.
    """
    distances = rim_distance_map(mask, width_px)
    boost = float(boost_normalized)
    result = np.zeros_like(distances, dtype=float)
    if boost <= 0.0 or not np.any(distances >= 0):
        return result

    width = max(1, int(width_px))
    normalized_profile = str(profile or "flat").lower()
    if normalized_profile == "flat":
        result[distances >= 0] = boost
    elif normalized_profile in {"linear", "smooth"}:
        active = distances >= 0
        t = np.clip(1.0 - (distances.astype(float) / float(width)), 0.0, 1.0)
        if normalized_profile == "smooth":
            t = t * t * (3.0 - 2.0 * t)
        result[active] = t[active] * boost
    else:
        raise ValueError("rim profile must be 'flat', 'linear' or 'smooth'")
    return result


def apply_outer_rim_to_heightmap(
    heightmap,
    mask,
    width_px=0,
    rim_height_mm=0.0,
    relief_height_mm=1.0,
    profile="flat",
):
    """Raise foreground boundary cells in the heightmap to create a simple rim.

    The heightmap remains normalized. The requested rim height is converted into
    normalized units by dividing by relief_height_mm, then added to rim cells and
    clipped to 1.0 for this MVP path. Linear and smooth profiles taper the boost
    inward.
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
    normalized_profile = str(profile or "flat").lower()
    report = {
        "enabled": False,
        "rim_width_px": max(0, width),
        "rim_height_mm": height_mm,
        "rim_profile": normalized_profile,
        "rim_pixel_count": 0,
        "boost_normalized": 0.0,
        "clipped_pixel_count": 0,
    }
    if width <= 0 or height_mm <= 0.0 or relief_mm <= 0.0 or not mask.any():
        return heightmap.copy(), report

    boost = height_mm / relief_mm
    boost_map = rim_boost_map(mask, width_px=width, boost_normalized=boost, profile=normalized_profile)
    rim = boost_map > 0.0
    result = heightmap.copy()
    after_unclipped = result[rim] + boost_map[rim]
    result[rim] = np.clip(after_unclipped, 0.0, 1.0)
    report.update(
        {
            "enabled": bool(rim.any()),
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
