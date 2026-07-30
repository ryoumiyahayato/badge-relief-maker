"""Connected-region and contour-ready mask extraction helpers."""

import numpy as np

from .components import connected_components


def bounding_box(mask):
    """Return a simple box for a mask."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def connected_regions(mask, minimum_pixels=1, connectivity=4):
    """Return deterministic boolean masks for connected foreground regions."""
    mask = np.asarray(mask, dtype=bool)
    minimum = max(1, int(minimum_pixels))
    regions = []
    for component in connected_components(mask, connectivity=connectivity):
        if len(component.pixels) < minimum:
            continue
        region = np.zeros(mask.shape, dtype=bool)
        row_values, col_values = zip(*component.pixels)
        region[np.asarray(row_values), np.asarray(col_values)] = True
        regions.append(region)
    regions.sort(key=lambda region: (-int(region.sum()), bounding_box(region)))
    return regions


def region_report(mask, minimum_pixels=1, connectivity=4):
    regions = connected_regions(mask, minimum_pixels=minimum_pixels, connectivity=connectivity)
    return {
        "region_count": len(regions),
        "pixel_counts": [int(region.sum()) for region in regions],
        "bounding_boxes": [bounding_box(region) for region in regions],
        "connectivity": int(connectivity),
    }
