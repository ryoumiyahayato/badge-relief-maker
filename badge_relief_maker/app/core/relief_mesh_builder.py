"""Relief mesh generation from a heightmap."""

import numpy as np


def build_grid_surface(heightmap, width_mm, height_mm, relief_height_mm):
    """Build a simple triangular grid surface from a heightmap."""
    rows, cols = heightmap.shape
    xs = np.linspace(0, width_mm, cols)
    ys = np.linspace(0, height_mm, rows)
    xx, yy = np.meshgrid(xs, ys)
    zz = heightmap.astype(float) * relief_height_mm
    vertices = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])

    faces = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            i0 = r * cols + c
            i1 = i0 + 1
            i2 = i0 + cols
            i3 = i2 + 1
            faces.append([i0, i2, i1])
            faces.append([i1, i2, i3])
    return vertices, np.asarray(faces, dtype=np.int64)
