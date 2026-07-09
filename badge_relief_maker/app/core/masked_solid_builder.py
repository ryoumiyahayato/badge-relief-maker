"""Build a mask footprint relief solid.

This module is still a simple MVP implementation. It creates one cuboid-like
relief cell for every foreground pixel. That is heavier than an optimized mesh,
but it proves that the model can follow the foreground mask instead of always
using a full rectangle.
"""

import numpy as np

from .contour_side_builder import build_contour_side_walls


def _mesh_arrays(vertices, faces):
    """Return mesh arrays with stable two-dimensional shapes."""
    if len(vertices) == 0:
        vertices_array = np.zeros((0, 3), dtype=float)
    else:
        vertices_array = np.asarray(vertices, dtype=float).reshape((-1, 3))

    if len(faces) == 0:
        faces_array = np.zeros((0, 3), dtype=np.int64)
    else:
        faces_array = np.asarray(faces, dtype=np.int64).reshape((-1, 3))
    return vertices_array, faces_array


def _append_mesh(vertices, faces, add_vertices, add_faces):
    """Append one mesh into vertex and face lists."""
    if len(add_vertices) == 0:
        return vertices, faces
    offset = len(vertices)
    vertices.extend(np.asarray(add_vertices, dtype=float).tolist())
    faces.extend((np.asarray(add_faces, dtype=np.int64) + offset).tolist())
    return vertices, faces


def build_masked_relief_solid(heightmap, mask, width_mm, height_mm, base_thickness_mm, relief_height_mm):
    """Create a relief solid whose footprint follows a boolean mask.

    External boundary walls are generated through the contour side builder.
    Internal edges between two foreground cells are also closed when their top
    heights differ, so stepped relief levels do not leave open vertical cracks.
    """
    if heightmap.shape != mask.shape:
        raise ValueError("heightmap and mask must have the same shape")

    rows, cols = heightmap.shape
    if rows <= 0 or cols <= 0:
        raise ValueError("heightmap and mask must be non-empty 2D arrays")

    cell_w = float(width_mm) / float(cols)
    cell_h = float(height_mm) / float(rows)
    top_z_values = heightmap.astype(float) * float(relief_height_mm)
    z_bottom = -float(base_thickness_mm)
    vertices = []
    faces = []

    def add_vertex(x, y, z):
        vertices.append([x, y, z])
        return len(vertices) - 1

    def add_quad(a, b, c, d):
        faces.append([a, b, c])
        faces.append([a, c, d])

    def add_vertical_quad(x0, y0, x1, y1, z_low, z_high):
        if abs(float(z_high) - float(z_low)) < 1e-9:
            return
        a = add_vertex(x0, y0, z_low)
        b = add_vertex(x1, y1, z_low)
        c = add_vertex(x1, y1, z_high)
        d = add_vertex(x0, y0, z_high)
        add_quad(a, b, c, d)

    for r in range(rows):
        for c in range(cols):
            if not bool(mask[r, c]):
                continue

            x0 = c * cell_w
            x1 = (c + 1) * cell_w
            y0 = r * cell_h
            y1 = (r + 1) * cell_h
            z_top = float(top_z_values[r, c])

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

            if r > 0 and bool(mask[r - 1, c]) and z_top > float(top_z_values[r - 1, c]):
                add_vertical_quad(x0, y0, x1, y0, float(top_z_values[r - 1, c]), z_top)

            if r < rows - 1 and bool(mask[r + 1, c]) and z_top > float(top_z_values[r + 1, c]):
                add_vertical_quad(x0, y1, x1, y1, float(top_z_values[r + 1, c]), z_top)

            if c > 0 and bool(mask[r, c - 1]) and z_top > float(top_z_values[r, c - 1]):
                add_vertical_quad(x0, y0, x0, y1, float(top_z_values[r, c - 1]), z_top)

            if c < cols - 1 and bool(mask[r, c + 1]) and z_top > float(top_z_values[r, c + 1]):
                add_vertical_quad(x1, y0, x1, y1, float(top_z_values[r, c + 1]), z_top)

    side_vertices, side_faces = build_contour_side_walls(
        heightmap,
        mask,
        width_mm,
        height_mm,
        base_thickness_mm,
        relief_height_mm,
    )
    _append_mesh(vertices, faces, side_vertices, side_faces)
    return _mesh_arrays(vertices, faces)
