"""Connected-region and contour-ready mask extraction helpers."""

from collections import deque
import numpy as np


def bounding_box(mask):
    """Return a simple box for a mask."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def placeholder_regions(mask):
    """Backward-compatible alias returning all four-connected regions."""
    return connected_regions(mask)


def connected_regions(mask, minimum_pixels=1, connectivity=4):
    """Return deterministic boolean masks for connected foreground regions."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")
    if connectivity not in {4, 8}:
        raise ValueError("connectivity must be 4 or 8")
    minimum = max(1, int(minimum_pixels))
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if connectivity == 8:
        offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    visited = np.zeros(mask.shape, dtype=bool)
    regions = []
    rows, cols = mask.shape
    for start_row, start_col in zip(*np.nonzero(mask)):
        if visited[start_row, start_col]:
            continue
        visited[start_row, start_col] = True
        queue = deque([(int(start_row), int(start_col))])
        pixels = []
        while queue:
            row, col = queue.popleft()
            pixels.append((row, col))
            for row_delta, col_delta in offsets:
                next_row, next_col = row + row_delta, col + col_delta
                if 0 <= next_row < rows and 0 <= next_col < cols and mask[next_row, next_col] and not visited[next_row, next_col]:
                    visited[next_row, next_col] = True
                    queue.append((next_row, next_col))
        if len(pixels) >= minimum:
            region = np.zeros(mask.shape, dtype=bool)
            row_values, col_values = zip(*pixels)
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
