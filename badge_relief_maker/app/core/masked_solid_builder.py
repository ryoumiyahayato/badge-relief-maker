"""Build a closed relief solid from a masked height field."""

from collections import deque

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


def _component_labels(mask):
    """Label four-connected foreground cells so separate parts keep separate vertices."""
    rows, cols = mask.shape
    labels = np.full(mask.shape, -1, dtype=np.int64)
    component = 0
    for start_row, start_col in zip(*np.nonzero(mask)):
        if labels[start_row, start_col] >= 0:
            continue
        labels[start_row, start_col] = component
        queue = deque([(int(start_row), int(start_col))])
        while queue:
            row, col = queue.popleft()
            for next_row, next_col in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if 0 <= next_row < rows and 0 <= next_col < cols:
                    if mask[next_row, next_col] and labels[next_row, next_col] < 0:
                        labels[next_row, next_col] = component
                        queue.append((next_row, next_col))
        component += 1
    return labels, component


def _corner_heights(top_z, labels, component_count):
    """Average incident cell heights at shared grid corners for a continuous top."""
    rows, cols = top_z.shape
    sums = [np.zeros((rows + 1, cols + 1), dtype=float) for _ in range(component_count)]
    counts = [np.zeros((rows + 1, cols + 1), dtype=np.int64) for _ in range(component_count)]
    for row, col in zip(*np.nonzero(labels >= 0)):
        component = int(labels[row, col])
        value = float(top_z[row, col])
        for corner_row, corner_col in ((row, col), (row, col + 1), (row + 1, col + 1), (row + 1, col)):
            sums[component][corner_row, corner_col] += value
            counts[component][corner_row, corner_col] += 1

    result = []
    for component in range(component_count):
        values = np.zeros_like(sums[component])
        used = counts[component] > 0
        values[used] = sums[component][used] / counts[component][used]
        result.append(values)
    return result


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
    """Create a closed indexed height-field solid whose footprint follows ``mask``.

    Foreground pixels are treated as rectangular cells. Heights are averaged at
    shared cell corners, giving adjacent cells one continuous top edge instead of
    separate plateaus joined by T-junction-prone step walls. Four-connected mask
    components use separate vertex namespaces, and outer walls reuse the same top
    and bottom vertices as the horizontal surfaces.

    ``use_smoothed_side_walls`` and ``contour_smoothing_iterations`` remain in the
    signature for project compatibility. The manufacturing path currently favors
    the closed indexed surface over the older non-watertight smoothed preview wall.
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
    labels, component_count = _component_labels(mask)
    corner_heights = _corner_heights(top_z, labels, component_count)

    vertices = []
    faces = []
    vertex_index = {}

    def x_coord(grid_x):
        return (float(grid_x) - float(col_min)) * cell_w

    def y_coord(grid_y):
        return (float(grid_y) - float(row_min)) * cell_h

    def point(component, grid_row, grid_col, z):
        key = (int(component), int(grid_row), int(grid_col), float(z))
        index = vertex_index.get(key)
        if index is None:
            index = len(vertices)
            vertex_index[key] = index
            vertices.append([x_coord(grid_col), y_coord(grid_row), float(z)])
        return index

    def quad(a, b, c, d):
        faces.append([a, b, c])
        faces.append([a, c, d])

    rows, cols = mask.shape
    for row, col in zip(*np.nonzero(mask)):
        component = int(labels[row, col])
        heights = corner_heights[component]
        top00 = point(component, row, col, heights[row, col])
        top10 = point(component, row, col + 1, heights[row, col + 1])
        top11 = point(component, row + 1, col + 1, heights[row + 1, col + 1])
        top01 = point(component, row + 1, col, heights[row + 1, col])
        bottom00 = point(component, row, col, z_bottom)
        bottom10 = point(component, row, col + 1, z_bottom)
        bottom11 = point(component, row + 1, col + 1, z_bottom)
        bottom01 = point(component, row + 1, col, z_bottom)

        quad(top00, top10, top11, top01)
        quad(bottom00, bottom01, bottom11, bottom10)

        if row == 0 or labels[row - 1, col] != component:
            quad(bottom00, bottom10, top10, top00)
        if col == cols - 1 or labels[row, col + 1] != component:
            quad(bottom10, bottom11, top11, top10)
        if row == rows - 1 or labels[row + 1, col] != component:
            quad(bottom11, bottom01, top01, top11)
        if col == 0 or labels[row, col - 1] != component:
            quad(bottom01, bottom00, top00, top01)

    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)
