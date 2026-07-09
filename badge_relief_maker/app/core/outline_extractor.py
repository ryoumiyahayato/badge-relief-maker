"""Mask outline extraction helpers.

These functions do not yet build a smoothed contour mesh. They extract the grid
boundary of a foreground mask so the pipeline can report outline complexity and
later replace pixel-cell side closure with contour-based side closure.
"""

from collections import defaultdict

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


def trace_boundary_loops(edges):
    """Trace oriented boundary edges into closed or partial loops.

    Grid masks can create multiple loops when the foreground has separated
    components or holes. This tracer is deterministic and conservative; ambiguous
    branch points are kept as separate partial loops instead of guessed curves.
    """
    normalized_edges = [(_point_tuple(a), _point_tuple(b)) for a, b in edges]
    unused = set(normalized_edges)
    outgoing = defaultdict(list)
    for start, end in normalized_edges:
        outgoing[start].append(end)

    loops = []
    while unused:
        start, end = min(unused)
        unused.remove((start, end))
        loop = [start, end]
        current = end
        guard = 0
        while current != start and guard <= len(normalized_edges):
            guard += 1
            candidates = sorted(outgoing.get(current, []))
            next_edge = None
            for candidate in candidates:
                edge = (current, candidate)
                if edge in unused:
                    next_edge = edge
                    break
            if next_edge is None:
                break
            unused.remove(next_edge)
            current = next_edge[1]
            loop.append(current)
        loops.append(loop)
    return loops


def simplify_collinear_points(points):
    """Remove collinear points from a traced grid contour."""
    pts = [_point_tuple(item) for item in points]
    if len(pts) <= 3:
        return pts

    closed = pts[0] == pts[-1]
    work = pts[:-1] if closed else pts[:]
    if len(work) <= 3:
        return pts

    simplified = []
    count = len(work)
    for index, point in enumerate(work):
        if closed:
            previous_point = work[(index - 1) % count]
            next_point = work[(index + 1) % count]
        else:
            if index == 0 or index == count - 1:
                simplified.append(point)
                continue
            previous_point = work[index - 1]
            next_point = work[index + 1]

        if _is_collinear(previous_point, point, next_point):
            continue
        simplified.append(point)

    if closed and simplified and simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified


def outline_report(mask, width_mm, height_mm):
    """Return lightweight outline metrics for a mask footprint."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")
    rows, cols = mask.shape
    if rows <= 0 or cols <= 0:
        raise ValueError("mask must be non-empty")

    edges = boundary_edges_from_mask(mask)
    loops = trace_boundary_loops(edges)
    simplified_loops = [simplify_collinear_points(loop) for loop in loops]
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
        "loop_count": int(len(loops)),
        "loop_point_count": int(sum(len(loop) for loop in loops)),
        "simplified_loop_point_count": int(sum(len(loop) for loop in simplified_loops)),
        "largest_loop_point_count": int(max((len(loop) for loop in loops), default=0)),
        "largest_simplified_loop_point_count": int(max((len(loop) for loop in simplified_loops), default=0)),
    }


def _point_tuple(point):
    return (int(point[0]), int(point[1]))


def _is_collinear(a, b, c):
    ab = (b[0] - a[0], b[1] - a[1])
    bc = (c[0] - b[0], c[1] - b[1])
    return ab[0] * bc[1] - ab[1] * bc[0] == 0


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
