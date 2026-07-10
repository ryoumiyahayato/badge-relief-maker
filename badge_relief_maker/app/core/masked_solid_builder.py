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


def _boundary_inward_vectors(mask, labels):
    """Return per-component grid-corner vectors pointing into foreground."""
    rows, cols = mask.shape
    vectors = {}

    def add(component, row, col, dx, dy):
        key = (int(component), int(row), int(col))
        old_x, old_y = vectors.get(key, (0.0, 0.0))
        vectors[key] = (old_x + dx, old_y + dy)

    for row, col in zip(*np.nonzero(mask)):
        component = int(labels[row, col])
        if row == 0 or labels[row - 1, col] != component:
            add(component, row, col, 0.0, 1.0)
            add(component, row, col + 1, 0.0, 1.0)
        if col == cols - 1 or labels[row, col + 1] != component:
            add(component, row, col + 1, -1.0, 0.0)
            add(component, row + 1, col + 1, -1.0, 0.0)
        if row == rows - 1 or labels[row + 1, col] != component:
            add(component, row + 1, col + 1, 0.0, -1.0)
            add(component, row + 1, col, 0.0, -1.0)
        if col == 0 or labels[row, col - 1] != component:
            add(component, row + 1, col, 1.0, 0.0)
            add(component, row, col, 1.0, 0.0)

    normalized = {}
    for key, (dx, dy) in vectors.items():
        scale = max(abs(dx), abs(dy), 1.0)
        normalized[key] = (dx / scale, dy / scale)
    return normalized


def _profile_settings(edge_style, bevel_mm, radius_mm, cell_w, cell_h):
    style = str(edge_style or "straight").lower()
    if style not in {"straight", "sloped", "bevel", "rounded"}:
        raise ValueError("edge_style must be straight, sloped, bevel or rounded")
    requested = float(radius_mm if style == "rounded" else bevel_mm)
    if style == "sloped" and requested <= 0.0:
        requested = min(cell_w, cell_h) * 0.25
    inset = min(max(requested, 0.0), min(cell_w, cell_h) * 0.45)
    if inset <= 0.0:
        style = "straight"
    segments = 4 if style == "rounded" else 1
    return style, inset, segments


def _build_indexed_solid(
    top_z,
    bottom_z,
    mask,
    width_mm,
    height_mm,
    edge_style="straight",
    bevel_mm=0.0,
    radius_mm=0.0,
    profile_both_sides=False,
):
    """Build an oriented closed solid between arbitrary top and bottom fields."""
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return _empty_mesh()
    ys, xs = np.nonzero(mask)
    row_min, row_max = int(ys.min()), int(ys.max())
    col_min, col_max = int(xs.min()), int(xs.max())
    foreground_rows = row_max - row_min + 1
    foreground_cols = col_max - col_min + 1
    cell_w = float(width_mm) / float(foreground_cols)
    cell_h = float(height_mm) / float(foreground_rows)
    labels, component_count = _component_labels(mask)
    top_corners = _corner_heights(np.asarray(top_z, dtype=float), labels, component_count)
    bottom_corners = _corner_heights(np.asarray(bottom_z, dtype=float), labels, component_count)
    inward_vectors = _boundary_inward_vectors(mask, labels)
    style, inset, segments = _profile_settings(edge_style, bevel_mm, radius_mm, cell_w, cell_h)

    vertices = []
    faces = []
    vertex_index = {}

    def base_xy(grid_row, grid_col):
        return (float(grid_col) - float(col_min)) * cell_w, (float(grid_row) - float(row_min)) * cell_h

    def vertex(component, grid_row, grid_col, level, x, y, z):
        key = (int(component), int(grid_row), int(grid_col), str(level))
        index = vertex_index.get(key)
        if index is None:
            index = len(vertices)
            vertex_index[key] = index
            vertices.append([float(x), float(y), float(z)])
        return index

    def profile(component, grid_row, grid_col):
        x, y = base_xy(grid_row, grid_col)
        bottom = float(bottom_corners[component][grid_row, grid_col])
        top = float(top_corners[component][grid_row, grid_col])
        dx, dy = inward_vectors.get((component, grid_row, grid_col), (0.0, 0.0))
        if style == "straight" or (dx == 0.0 and dy == 0.0):
            return [
                vertex(component, grid_row, grid_col, "bottom", x, y, bottom),
                vertex(component, grid_row, grid_col, "top", x, y, top),
            ]

        available = max(top - bottom, 0.0)
        depth = min(inset, available / (2.0 if profile_both_sides else 1.0))
        if depth <= 1e-12:
            return [
                vertex(component, grid_row, grid_col, "bottom", x, y, bottom),
                vertex(component, grid_row, grid_col, "top", x, y, top),
            ]
        shift_x, shift_y = dx * inset, dy * inset
        points = []
        if profile_both_sides:
            points.append(vertex(component, grid_row, grid_col, "bottom", x + shift_x, y + shift_y, bottom))
            if style == "rounded":
                for index in range(1, segments + 1):
                    theta = (np.pi / 2.0) * float(index) / float(segments)
                    fraction = np.cos(theta)
                    z = bottom + depth * np.sin(theta)
                    points.append(vertex(component, grid_row, grid_col, f"lower_round_{index}", x + shift_x * fraction, y + shift_y * fraction, z))
            else:
                points.append(vertex(component, grid_row, grid_col, "lower_bevel", x, y, bottom + depth))
        else:
            points.append(vertex(component, grid_row, grid_col, "bottom", x, y, bottom))

        top_profile_start = top - depth
        last_point = vertices[points[-1]]
        if not np.allclose(last_point, [x, y, top_profile_start], atol=1e-12, rtol=0.0):
            points.append(vertex(component, grid_row, grid_col, "upper_start", x, y, top_profile_start))
        if style == "rounded":
            for index in range(1, segments + 1):
                theta = (np.pi / 2.0) * float(index) / float(segments)
                fraction = 1.0 - np.cos(theta)
                z = top_profile_start + depth * np.sin(theta)
                points.append(vertex(component, grid_row, grid_col, f"upper_round_{index}", x + shift_x * fraction, y + shift_y * fraction, z))
        else:
            points.append(vertex(component, grid_row, grid_col, "top", x + shift_x, y + shift_y, top))
        return points

    def top_vertex(component, row, col):
        if (component, row, col) in inward_vectors:
            return profile(component, row, col)[-1]
        x, y = base_xy(row, col)
        return vertex(component, row, col, "top", x, y, top_corners[component][row, col])

    def bottom_vertex(component, row, col):
        if (component, row, col) in inward_vectors:
            return profile(component, row, col)[0]
        x, y = base_xy(row, col)
        return vertex(component, row, col, "bottom", x, y, bottom_corners[component][row, col])

    def quad(a, b, c, d):
        faces.append([a, b, c])
        faces.append([a, c, d])

    def wall(component, first, second):
        first_profile = profile(component, *first)
        second_profile = profile(component, *second)
        if len(first_profile) != len(second_profile):
            raise RuntimeError("edge profile vertex count mismatch")
        for index in range(len(first_profile) - 1):
            quad(first_profile[index], second_profile[index], second_profile[index + 1], first_profile[index + 1])

    rows, cols = mask.shape
    for row, col in zip(*np.nonzero(mask)):
        component = int(labels[row, col])
        top00, top10 = top_vertex(component, row, col), top_vertex(component, row, col + 1)
        top11, top01 = top_vertex(component, row + 1, col + 1), top_vertex(component, row + 1, col)
        bottom00, bottom10 = bottom_vertex(component, row, col), bottom_vertex(component, row, col + 1)
        bottom11, bottom01 = bottom_vertex(component, row + 1, col + 1), bottom_vertex(component, row + 1, col)
        quad(top00, top10, top11, top01)
        quad(bottom00, bottom01, bottom11, bottom10)

        if row == 0 or labels[row - 1, col] != component:
            wall(component, (row, col), (row, col + 1))
        if col == cols - 1 or labels[row, col + 1] != component:
            wall(component, (row, col + 1), (row + 1, col + 1))
        if row == rows - 1 or labels[row + 1, col] != component:
            wall(component, (row + 1, col + 1), (row + 1, col))
        if col == 0 or labels[row, col - 1] != component:
            wall(component, (row + 1, col), (row, col))

    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)


def build_masked_relief_solid(
    heightmap,
    mask,
    width_mm,
    height_mm,
    base_thickness_mm,
    relief_height_mm,
    use_smoothed_side_walls=False,
    contour_smoothing_iterations=1,
    edge_style="straight",
    bevel_mm=0.0,
    radius_mm=0.0,
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

    top_z = np.clip(heightmap, 0.0, 1.0) * float(relief_height_mm)
    bottom_z = np.full(heightmap.shape, -float(base_thickness_mm), dtype=float)
    return _build_indexed_solid(
        top_z,
        bottom_z,
        mask,
        width_mm,
        height_mm,
        edge_style=edge_style,
        bevel_mm=bevel_mm,
        radius_mm=radius_mm,
        profile_both_sides=False,
    )


def build_double_sided_relief_solid(
    front_heightmap,
    back_heightmap,
    mask,
    width_mm,
    height_mm,
    body_thickness_mm,
    front_relief_height_mm,
    back_relief_height_mm,
    edge_style="straight",
    bevel_mm=0.0,
    radius_mm=0.0,
):
    """Build one fused body with front relief at +Z and back relief at -Z."""
    front = np.asarray(front_heightmap, dtype=float)
    back = np.asarray(back_heightmap, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if front.shape != back.shape or front.shape != mask.shape or front.ndim != 2:
        raise ValueError("front heightmap, back heightmap and mask must share one 2D shape")
    if not np.isfinite(front).all() or not np.isfinite(back).all():
        raise ValueError("double-side heightmaps must contain finite values")
    if float(body_thickness_mm) <= 0.0:
        raise ValueError("body_thickness_mm must be positive")
    half_body = float(body_thickness_mm) / 2.0
    top_z = half_body + np.clip(front, 0.0, 1.0) * float(front_relief_height_mm)
    bottom_z = -half_body - np.clip(back, 0.0, 1.0) * float(back_relief_height_mm)
    return _build_indexed_solid(
        top_z,
        bottom_z,
        mask,
        width_mm,
        height_mm,
        edge_style=edge_style,
        bevel_mm=bevel_mm,
        radius_mm=radius_mm,
        profile_both_sides=True,
    )


def build_layered_relief_solid(
    heightmap,
    mask,
    width_mm,
    height_mm,
    base_thickness_mm,
    relief_height_mm,
    max_levels=64,
):
    """Build exact flat plateaus with a globally conforming Z-layer grid.

    This path is intended for explicit region layers. Every vertical wall is
    split at the same global height levels, so sharp steps remain watertight and
    do not create T-junctions.
    """
    heightmap, mask = _validate_inputs(heightmap, mask, width_mm, height_mm, base_thickness_mm, relief_height_mm)
    if not mask.any():
        return _empty_mesh()
    top_z = np.clip(heightmap, 0.0, 1.0) * float(relief_height_mm)
    unique_top = np.unique(np.round(top_z[mask], 9))
    if len(unique_top) > int(max_levels):
        raise ValueError(f"layered height mode supports at most {int(max_levels)} distinct height levels")
    levels = np.unique(np.concatenate(([-float(base_thickness_mm)], unique_top))).astype(float)
    levels.sort()
    if len(levels) < 2:
        raise ValueError("layered solid requires positive base or relief thickness")

    ys, xs = np.nonzero(mask)
    row_min, row_max = int(ys.min()), int(ys.max())
    col_min, col_max = int(xs.min()), int(xs.max())
    cell_w = float(width_mm) / float(col_max - col_min + 1)
    cell_h = float(height_mm) / float(row_max - row_min + 1)
    labels, _ = _component_labels(mask)
    rows, cols = mask.shape
    occupied = np.zeros((len(levels) - 1, rows, cols), dtype=bool)
    for level_index in range(len(levels) - 1):
        upper = levels[level_index + 1]
        occupied[level_index] = mask & (top_z >= upper - 1e-9)

    vertices = []
    faces = []
    indices = {}

    def point(component, row, col, z):
        key = (int(component), int(row), int(col), round(float(z), 9))
        index = indices.get(key)
        if index is None:
            index = len(vertices)
            indices[key] = index
            vertices.append([(col - col_min) * cell_w, (row - row_min) * cell_h, float(z)])
        return index

    def quad(a, b, c, d):
        faces.append([a, b, c])
        faces.append([a, c, d])

    for level_index, row, col in zip(*np.nonzero(occupied)):
        component = int(labels[row, col])
        lower, upper = levels[level_index], levels[level_index + 1]
        b00, b10 = point(component, row, col, lower), point(component, row, col + 1, lower)
        b11, b01 = point(component, row + 1, col + 1, lower), point(component, row + 1, col, lower)
        t00, t10 = point(component, row, col, upper), point(component, row, col + 1, upper)
        t11, t01 = point(component, row + 1, col + 1, upper), point(component, row + 1, col, upper)
        below = level_index > 0 and occupied[level_index - 1, row, col]
        above = level_index < len(levels) - 2 and occupied[level_index + 1, row, col]
        if not below:
            quad(b00, b01, b11, b10)
        if not above:
            quad(t00, t10, t11, t01)
        if row == 0 or not occupied[level_index, row - 1, col]:
            quad(b00, b10, t10, t00)
        if col == cols - 1 or not occupied[level_index, row, col + 1]:
            quad(b10, b11, t11, t10)
        if row == rows - 1 or not occupied[level_index, row + 1, col]:
            quad(b11, b01, t01, t11)
        if col == 0 or not occupied[level_index, row, col - 1]:
            quad(b01, b00, t00, t01)
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)
