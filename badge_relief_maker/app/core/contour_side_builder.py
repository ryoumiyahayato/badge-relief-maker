"""Contour side wall mesh builder.

This module converts the external mask boundary into vertical side wall faces.
It is still grid-contour based, but it separates side closure from the per-cell
relief surface builder so later smoothing and bevel logic can replace this layer
without rewriting the whole relief pipeline.
"""

import numpy as np


def _empty_mesh():
    return np.zeros((0, 3), dtype=float), np.zeros((0, 3), dtype=np.int64)


def build_contour_side_walls(heightmap, mask, width_mm, height_mm, base_thickness_mm, relief_height_mm):
    """Build external side walls from the foreground mask boundary.

    The top side of each wall follows the top height of the foreground cell
    adjacent to that boundary edge. Internal step walls are intentionally not
    generated here; they remain part of the relief surface builder.
    """
    heightmap = np.asarray(heightmap, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if heightmap.shape != mask.shape:
        raise ValueError("heightmap and mask must have the same shape")
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")

    rows, cols = mask.shape
    if rows <= 0 or cols <= 0:
        raise ValueError("heightmap and mask must be non-empty 2D arrays")
    if not mask.any():
        return _empty_mesh()

    cell_w = float(width_mm) / float(cols)
    cell_h = float(height_mm) / float(rows)
    top_z_values = heightmap * float(relief_height_mm)
    z_bottom = -float(base_thickness_mm)
    vertices = []
    faces = []

    def add_vertex(x, y, z):
        vertices.append([float(x), float(y), float(z)])
        return len(vertices) - 1

    def add_wall(x0, y0, x1, y1, z_top):
        if abs(float(z_top) - float(z_bottom)) < 1e-12:
            return
        a = add_vertex(x0, y0, z_bottom)
        b = add_vertex(x1, y1, z_bottom)
        c = add_vertex(x1, y1, z_top)
        d = add_vertex(x0, y0, z_top)
        faces.append([a, b, c])
        faces.append([a, c, d])

    for r in range(rows):
        for c in range(cols):
            if not bool(mask[r, c]):
                continue

            x0 = c * cell_w
            x1 = (c + 1) * cell_w
            y0 = r * cell_h
            y1 = (r + 1) * cell_h
            z_top = float(top_z_values[r, c])

            if r == 0 or not bool(mask[r - 1, c]):
                add_wall(x0, y0, x1, y0, z_top)
            if c == cols - 1 or not bool(mask[r, c + 1]):
                add_wall(x1, y0, x1, y1, z_top)
            if r == rows - 1 or not bool(mask[r + 1, c]):
                add_wall(x1, y1, x0, y1, z_top)
            if c == 0 or not bool(mask[r, c - 1]):
                add_wall(x0, y1, x0, y0, z_top)

    if not vertices:
        return _empty_mesh()
    return np.asarray(vertices, dtype=float).reshape((-1, 3)), np.asarray(faces, dtype=np.int64).reshape((-1, 3))
