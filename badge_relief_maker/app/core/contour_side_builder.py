"""Contour side wall mesh builder.

This module converts the external mask boundary into vertical side wall faces.
The default builder is grid-contour based. The smoothed builder uses simplified
and Chaikin-smoothed contour loops as a preview path for later bevel/rim work.
"""

import numpy as np

from .outline_extractor import (
    boundary_edges_from_mask,
    scale_loop_to_mm,
    simplify_collinear_points,
    smooth_closed_loop,
    trace_boundary_loops,
)


def _empty_mesh():
    return np.zeros((0, 3), dtype=float), np.zeros((0, 3), dtype=np.int64)


def _validate_inputs(heightmap, mask):
    heightmap = np.asarray(heightmap, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if heightmap.shape != mask.shape:
        raise ValueError("heightmap and mask must have the same shape")
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")
    rows, cols = mask.shape
    if rows <= 0 or cols <= 0:
        raise ValueError("heightmap and mask must be non-empty 2D arrays")
    return heightmap, mask, rows, cols


def build_contour_side_walls(heightmap, mask, width_mm, height_mm, base_thickness_mm, relief_height_mm):
    """Build external side walls from the foreground mask boundary.

    The top side of each wall follows the top height of the foreground cell
    adjacent to that boundary edge. Internal step walls are intentionally not
    generated here; they remain part of the relief surface builder.
    """
    heightmap, mask, rows, cols = _validate_inputs(heightmap, mask)
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

    return _mesh_arrays(vertices, faces)


def build_smoothed_contour_side_walls(
    heightmap,
    mask,
    width_mm,
    height_mm,
    base_thickness_mm,
    relief_height_mm,
    smoothing_iterations=1,
):
    """Build preview side walls from smoothed external contour loops.

    This is not yet the default production path because smoothed contour walls
    may not perfectly share vertices with the pixel-cell top/bottom surfaces.
    It exists so the pipeline can start exposing and testing the smoother side
    wall generation layer before bevel/rim generation is added.
    """
    heightmap, mask, rows, cols = _validate_inputs(heightmap, mask)
    if not mask.any():
        return _empty_mesh()

    top_z_values = heightmap * float(relief_height_mm)
    z_bottom = -float(base_thickness_mm)
    edges = boundary_edges_from_mask(mask)
    loops = trace_boundary_loops(edges)
    vertices = []
    faces = []

    def add_vertex(x, y, z):
        vertices.append([float(x), float(y), float(z)])
        return len(vertices) - 1

    def add_wall(p0_grid, p1_grid, p0_mm, p1_mm):
        if _points_close(p0_grid, p1_grid):
            return
        midpoint = ((float(p0_grid[0]) + float(p1_grid[0])) * 0.5, (float(p0_grid[1]) + float(p1_grid[1])) * 0.5)
        z_top = _nearest_foreground_height(midpoint, mask, top_z_values)
        if abs(float(z_top) - float(z_bottom)) < 1e-12:
            return
        a = add_vertex(p0_mm[0], p0_mm[1], z_bottom)
        b = add_vertex(p1_mm[0], p1_mm[1], z_bottom)
        c = add_vertex(p1_mm[0], p1_mm[1], z_top)
        d = add_vertex(p0_mm[0], p0_mm[1], z_top)
        faces.append([a, b, c])
        faces.append([a, c, d])

    for loop in loops:
        simplified = simplify_collinear_points(loop)
        smoothed = smooth_closed_loop(simplified, iterations=smoothing_iterations)
        if len(smoothed) < 2:
            continue
        smoothed_mm = scale_loop_to_mm(smoothed, width_mm, height_mm, (rows, cols))
        for index in range(len(smoothed) - 1):
            add_wall(smoothed[index], smoothed[index + 1], smoothed_mm[index], smoothed_mm[index + 1])

    return _mesh_arrays(vertices, faces)


def _nearest_foreground_height(point, mask, top_z_values):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return 0.0
    centers_x = xs.astype(float) + 0.5
    centers_y = ys.astype(float) + 0.5
    dx = centers_x - float(point[0])
    dy = centers_y - float(point[1])
    index = int(np.argmin(dx * dx + dy * dy))
    return float(top_z_values[int(ys[index]), int(xs[index])])


def _points_close(a, b, epsilon=1e-9):
    return abs(float(a[0]) - float(b[0])) <= epsilon and abs(float(a[1]) - float(b[1])) <= epsilon


def _mesh_arrays(vertices, faces):
    if not vertices:
        return _empty_mesh()
    return np.asarray(vertices, dtype=float).reshape((-1, 3)), np.asarray(faces, dtype=np.int64).reshape((-1, 3))
