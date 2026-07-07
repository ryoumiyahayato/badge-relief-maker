"""Build a mask footprint relief solid.

This module is still a simple MVP implementation. It creates one cuboid-like
relief cell for every foreground pixel. That is heavier than an optimized mesh,
but it proves that the model can follow the foreground mask instead of always
using a full rectangle.
"""

import numpy as np


def build_masked_relief_solid(heightmap, mask, width_mm, height_mm, base_thickness_mm, relief_height_mm):
    """Create a relief solid whose footprint follows a boolean mask."""
    if heightmap.shape != mask.shape:
        raise ValueError("heightmap and mask must have the same shape")

    rows, cols = heightmap.shape
    cell_w = float(width_mm) / float(cols)
    cell_h = float(height_mm) / float(rows)
    vertices = []
    faces = []

    def add_vertex(x, y, z):
        vertices.append([x, y, z])
        return len(vertices) - 1

    def add_quad(a, b, c, d):
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
            z_top = float(heightmap[r, c]) * float(relief_height_mm)
            z_bottom = -float(base_thickness_mm)

            t00 = add_vertex(x0, y0, z_top)
            t10 = add_vertex(x1, y0, z_top)
            t11 = add_vertex(x1, y1, z_top)
            t01 = add_vertex(x0, y1, z_top)
            b00 = add_vertex(x0, y0, z_bottom)
            b10 = add_vertex(x1, y0, z_bottom)
            b11 = add_vertex(x1, y1, z_bottom)
            b01 = add_vertex(x0, y1, z_bottom)

            add_quad(t00, t10, t11, t01)
            add_quad(b00, b01, b11, b10)

            if r == 0 or not bool(mask[r - 1, c]):
                add_quad(t00, b00, b10, t10)
            if r == rows - 1 or not bool(mask[r + 1, c]):
                add_quad(t01, t11, b11, b01)
            if c == 0 or not bool(mask[r, c - 1]):
                add_quad(t00, t01, b01, b00)
            if c == cols - 1 or not bool(mask[r, c + 1]):
                add_quad(t10, b10, b11, t11)

    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)
