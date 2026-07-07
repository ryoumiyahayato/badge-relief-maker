"""Build a simple solid relief mesh from a heightmap."""

import numpy as np


def build_rectangular_relief_solid(heightmap, width_mm, height_mm, base_thickness_mm, relief_height_mm):
    """Create a rectangular solid with a raised top relief surface.

    This MVP builder uses the whole image rectangle as the footprint. Later
    versions should trim the footprint to the extracted outer contour.
    """
    rows, cols = heightmap.shape
    xs = np.linspace(0.0, float(width_mm), cols)
    ys = np.linspace(0.0, float(height_mm), rows)
    xx, yy = np.meshgrid(xs, ys)
    top_z = heightmap.astype(float) * float(relief_height_mm)
    bottom_z = np.full_like(top_z, -float(base_thickness_mm), dtype=float)

    top_vertices = np.column_stack([xx.ravel(), yy.ravel(), top_z.ravel()])
    bottom_vertices = np.column_stack([xx.ravel(), yy.ravel(), bottom_z.ravel()])
    vertices = np.vstack([top_vertices, bottom_vertices])

    faces = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            i0 = r * cols + c
            i1 = i0 + 1
            i2 = i0 + cols
            i3 = i2 + 1
            faces.append([i0, i2, i1])
            faces.append([i1, i2, i3])

            j0 = i0 + rows * cols
            j1 = i1 + rows * cols
            j2 = i2 + rows * cols
            j3 = i3 + rows * cols
            faces.append([j0, j1, j2])
            faces.append([j1, j3, j2])

    offset = rows * cols

    for c in range(cols - 1):
        top_a = c
        top_b = c + 1
        bot_a = top_a + offset
        bot_b = top_b + offset
        faces.append([top_a, bot_a, top_b])
        faces.append([top_b, bot_a, bot_b])

        top_a = (rows - 1) * cols + c
        top_b = top_a + 1
        bot_a = top_a + offset
        bot_b = top_b + offset
        faces.append([top_a, top_b, bot_a])
        faces.append([top_b, bot_b, bot_a])

    for r in range(rows - 1):
        top_a = r * cols
        top_b = top_a + cols
        bot_a = top_a + offset
        bot_b = top_b + offset
        faces.append([top_a, top_b, bot_a])
        faces.append([top_b, bot_b, bot_a])

        top_a = r * cols + cols - 1
        top_b = top_a + cols
        bot_a = top_a + offset
        bot_b = top_b + offset
        faces.append([top_a, bot_a, top_b])
        faces.append([top_b, bot_a, bot_b])

    return vertices, np.asarray(faces, dtype=np.int64)
