"""Build a closed relief solid from a masked height field."""

import numpy as np


def _empty_mesh():
    return np.zeros((0, 3), dtype=float), np.zeros((0, 3), dtype=np.int64)


def _validate_inputs(heightmap, mask, width_mm, height_mm, base_thickness_mm, relief_height_mm):
    heightmap = np.asarray(heightmap, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if heightmap.shape != mask.shape:
        raise ValueError("heightmap and mask must have the same shape")
    if heightmap.ndim != 2:
        raise ValueError("heightmap and mask must be 2D arrays")
    if heightmap.size == 0:
        raise ValueError("heightmap and mask must be non-empty 2D arrays")
    if not np.isfinite(heightmap).all():
        raise ValueError("heightmap contains non-finite values")
    if float(width_mm) <= 0.0 or float(height_mm) <= 0.0:
        raise ValueError("width_mm and height_mm must be positive")
    if float(base_thickness_mm) < 0.0 or float(relief_height_mm) < 0.0:
        raise ValueError("base and relief thickness must be non-negative")
    return heightmap, mask


def build_masked_relief_solid(
    heightmap,
    mask,
    width_mm,
    height_mm,
    base_thickness_mm,
    relief_height_mm,
    use_smoothed_side_walls=False,
    contour_smoothing_iterations=1,
):
    """Create a closed stepped relief solid whose footprint follows ``mask``.

    The surface is generated as horizontal cell faces plus vertical height slabs.
    Slab boundaries are split at every distinct neighboring height, preventing the
    T-junctions produced by attaching one unsplit outer wall to internal step walls.
    Vertices are shared by coordinate so every closed-surface edge can be paired.

    ``use_smoothed_side_walls`` and ``contour_smoothing_iterations`` remain in the
    signature for project compatibility. The manufacturing path currently favors
    the closed grid surface over the older non-watertight smoothed preview walls.
    """
    del use_smoothed_side_walls, contour_smoothing_iterations
    heightmap, mask = _validate_inputs(
        heightmap,
        mask,
        width_mm,
        height_mm,
        base_thickness_mm,
        relief_height_mm,
    )
    if not mask.any():
        return _empty_mesh()

    ys, xs = np.nonzero(mask)
    row_min = int(ys.min())
    row_max = int(ys.max())
    col_min = int(xs.min())
    col_max = int(xs.max())
    foreground_rows = row_max - row_min + 1
    foreground_cols = col_max - col_min + 1
    cell_w = float(width_mm) / float(foreground_cols)
    cell_h = float(height_mm) / float(foreground_rows)
    top_z = np.clip(heightmap, 0.0, 1.0) * float(relief_height_mm)
    z_bottom = -float(base_thickness_mm)

    vertices = []
    faces = []
    vertex_index = {}

    def point(x, y, z):
        key = (float(x), float(y), float(z))
        index = vertex_index.get(key)
        if index is None:
            index = len(vertices)
            vertex_index[key] = index
            vertices.append([key[0], key[1], key[2]])
        return index

    def x_coord(grid_x):
        return (float(grid_x) - float(col_min)) * cell_w

    def y_coord(grid_y):
        return (float(grid_y) - float(row_min)) * cell_h

    def quad(p0, p1, p2, p3):
        a = point(*p0)
        b = point(*p1)
        c = point(*p2)
        d = point(*p3)
        faces.append([a, b, c])
        faces.append([a, c, d])

    for row, col in zip(ys.tolist(), xs.tolist()):
        x0 = x_coord(col)
        x1 = x_coord(col + 1)
        y0 = y_coord(row)
        y1 = y_coord(row + 1)
        z_top = float(top_z[row, col])
        quad((x0, y0, z_top), (x1, y0, z_top), (x1, y1, z_top), (x0, y1, z_top))
        quad((x0, y0, z_bottom), (x0, y1, z_bottom), (x1, y1, z_bottom), (x1, y0, z_bottom))

    levels = sorted({z_bottom, *(float(value) for value in top_z[mask])})
    epsilon = 1e-12
    for z_low, z_high in zip(levels[:-1], levels[1:]):
        if z_high - z_low <= epsilon:
            continue
        occupied = mask & (top_z >= z_high - epsilon)
        for row, col in zip(*np.nonzero(occupied)):
            x0 = x_coord(col)
            x1 = x_coord(col + 1)
            y0 = y_coord(row)
            y1 = y_coord(row + 1)

            if row == 0 or not occupied[row - 1, col]:
                quad((x0, y0, z_low), (x1, y0, z_low), (x1, y0, z_high), (x0, y0, z_high))
            if col == occupied.shape[1] - 1 or not occupied[row, col + 1]:
                quad((x1, y0, z_low), (x1, y1, z_low), (x1, y1, z_high), (x1, y0, z_high))
            if row == occupied.shape[0] - 1 or not occupied[row + 1, col]:
                quad((x1, y1, z_low), (x0, y1, z_low), (x0, y1, z_high), (x1, y1, z_high))
            if col == 0 or not occupied[row, col - 1]:
                quad((x0, y1, z_low), (x0, y0, z_low), (x0, y0, z_high), (x0, y1, z_high))

    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)
