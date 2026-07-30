"""Feature-driven adaptive relief meshing with conforming hanging-edge splits."""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi

from .components import component_labels


@dataclass(frozen=True)
class AdaptiveLeaf:
    row0: int
    row1: int
    col0: int
    col1: int
    component: int


def detect_mesh_features(heightmap, mask, gradient_threshold=0.035, curvature_threshold=0.025, band_pixels=2):
    """Detect footprint contours, engraved lines and abrupt height changes."""
    values = np.asarray(heightmap, dtype=np.float32)
    footprint = np.asarray(mask, dtype=bool)
    if values.ndim != 2 or values.shape != footprint.shape:
        raise ValueError("heightmap and mask must be matching 2D arrays")
    eroded = ndi.binary_erosion(footprint)
    contour = footprint ^ eroded
    gradient_y = np.gradient(values, axis=0) if values.shape[0] > 1 else np.zeros_like(values)
    gradient_x = np.gradient(values, axis=1) if values.shape[1] > 1 else np.zeros_like(values)
    gradient = np.hypot(gradient_x, gradient_y)
    laplacian = np.abs(ndi.laplace(values))
    discontinuity = footprint & (gradient >= float(gradient_threshold))
    engraving = footprint & (laplacian >= float(curvature_threshold))
    raw = contour | discontinuity | engraving
    feature_band = ndi.binary_dilation(raw, iterations=max(0, int(band_pixels)))
    return feature_band, {
        "contour_pixel_count": int(contour.sum()),
        "height_discontinuity_pixel_count": int(discontinuity.sum()),
        "engraving_pixel_count": int(engraving.sum()),
        "refinement_band_pixel_count": int(feature_band.sum()),
        "gradient_threshold": float(gradient_threshold),
        "curvature_threshold": float(curvature_threshold),
        "band_pixels": int(max(0, band_pixels)),
    }


def _adaptive_leaves(mask, feature_map, labels, coarse_cell_px, discrete_values=None):
    rows, cols = mask.shape
    leaves = []

    def visit(row0, row1, col0, col1):
        local_mask = mask[row0:row1, col0:col1]
        if not local_mask.any():
            return
        height = row1 - row0
        width = col1 - col0
        mixed = not bool(local_mask.all())
        feature = bool(feature_map[row0:row1, col0:col1].any())
        if discrete_values is not None:
            local_values = discrete_values[row0:row1, col0:col1][local_mask]
            feature = feature or bool(local_values.size and np.ptp(local_values) > 1e-9)
        if height <= 1 and width <= 1:
            component = int(labels[row0, col0])
            if component >= 0:
                leaves.append(AdaptiveLeaf(row0, row1, col0, col1, component))
            return
        if not mixed and not feature:
            leaves.append(AdaptiveLeaf(row0, row1, col0, col1, int(labels[row0, col0])))
            return
        row_ranges = [(row0, row1)]
        col_ranges = [(col0, col1)]
        if height > 1:
            middle = row0 + height // 2
            row_ranges = [(row0, middle), (middle, row1)]
        if width > 1:
            middle = col0 + width // 2
            col_ranges = [(col0, middle), (middle, col1)]
        for next_rows in row_ranges:
            for next_cols in col_ranges:
                visit(next_rows[0], next_rows[1], next_cols[0], next_cols[1])

    block = max(1, int(coarse_cell_px))
    for row0 in range(0, rows, block):
        for col0 in range(0, cols, block):
            visit(row0, min(row0 + block, rows), col0, min(col0 + block, cols))
    return leaves


def _leaf_perimeter(leaf, horizontal_points, vertical_points):
    top = [(leaf.row0, value) for value in sorted(x for x in horizontal_points[leaf.row0] if leaf.col0 <= x <= leaf.col1)]
    right = [(value, leaf.col1) for value in sorted(y for y in vertical_points[leaf.col1] if leaf.row0 < y <= leaf.row1)]
    bottom = [
        (leaf.row1, value)
        for value in sorted((x for x in horizontal_points[leaf.row1] if leaf.col0 <= x < leaf.col1), reverse=True)
    ]
    left = [
        (value, leaf.col0)
        for value in sorted((y for y in vertical_points[leaf.col0] if leaf.row0 < y < leaf.row1), reverse=True)
    ]
    return top + right + bottom + left


def _build_adaptive_continuous_surfaces(
    top_values,
    bottom_values,
    footprint,
    width_mm,
    height_mm,
    features,
    feature_report,
    coarse_cell_px,
    strategy,
):
    """Triangulate two continuous surfaces through one conforming leaf grid."""
    labels, components = component_labels(footprint)
    leaves = _adaptive_leaves(footprint, features, labels, coarse_cell_px)
    horizontal_points = defaultdict(set)
    vertical_points = defaultdict(set)
    for leaf in leaves:
        for row, col in (
            (leaf.row0, leaf.col0),
            (leaf.row0, leaf.col1),
            (leaf.row1, leaf.col0),
            (leaf.row1, leaf.col1),
        ):
            horizontal_points[row].add(col)
            vertical_points[col].add(row)

    foreground_rows, foreground_cols = np.nonzero(footprint)
    row_min, row_max = int(foreground_rows.min()), int(foreground_rows.max())
    col_min, col_max = int(foreground_cols.min()), int(foreground_cols.max())
    cell_width = float(width_mm) / float(col_max - col_min + 1)
    cell_height = float(height_mm) / float(row_max - row_min + 1)
    vertices = []
    faces = []
    coordinate_vertices = {}
    perimeter_edges = {}
    edge_counts = defaultdict(int)

    def physical(row, col):
        return (float(col) - col_min) * cell_width, (float(row) - row_min) * cell_height

    def corner_height(field, component, row, col):
        samples = []
        for cell_row in (row - 1, row):
            for cell_col in (col - 1, col):
                if (
                    0 <= cell_row < footprint.shape[0]
                    and 0 <= cell_col < footprint.shape[1]
                    and int(labels[cell_row, cell_col]) == component
                ):
                    samples.append(float(field[cell_row, cell_col]))
        return float(np.mean(samples)) if samples else 0.0

    def coordinate_vertex(component, row, col, layer):
        key = (int(component), int(row), int(col), layer)
        index = coordinate_vertices.get(key)
        if index is None:
            x, y = physical(row, col)
            field = top_values if layer == "top" else bottom_values
            z = corner_height(field, component, row, col)
            index = len(vertices)
            coordinate_vertices[key] = index
            vertices.append([x, y, z])
        return index

    for leaf in leaves:
        perimeter = _leaf_perimeter(leaf, horizontal_points, vertical_points)
        if len(perimeter) < 4:
            continue
        x_center, y_center = physical((leaf.row0 + leaf.row1) / 2.0, (leaf.col0 + leaf.col1) / 2.0)
        local_top = top_values[leaf.row0 : leaf.row1, leaf.col0 : leaf.col1]
        local_bottom = bottom_values[leaf.row0 : leaf.row1, leaf.col0 : leaf.col1]
        top_center = len(vertices)
        vertices.append([x_center, y_center, float(local_top.mean())])
        bottom_center = len(vertices)
        vertices.append([x_center, y_center, float(local_bottom.mean())])
        top_ring = [coordinate_vertex(leaf.component, row, col, "top") for row, col in perimeter]
        bottom_ring = [coordinate_vertex(leaf.component, row, col, "bottom") for row, col in perimeter]
        for index in range(len(perimeter)):
            next_index = (index + 1) % len(perimeter)
            faces.append([top_center, top_ring[index], top_ring[next_index]])
            faces.append([bottom_center, bottom_ring[next_index], bottom_ring[index]])
            first, second = perimeter[index], perimeter[next_index]
            key = (leaf.component, tuple(sorted((first, second))))
            edge_counts[key] += 1
            perimeter_edges.setdefault(key, (leaf.component, first, second))

    wall_segment_count = 0
    for key, count in edge_counts.items():
        if count != 1:
            continue
        component, first, second = perimeter_edges[key]
        top_first = coordinate_vertex(component, first[0], first[1], "top")
        top_second = coordinate_vertex(component, second[0], second[1], "top")
        bottom_first = coordinate_vertex(component, first[0], first[1], "bottom")
        bottom_second = coordinate_vertex(component, second[0], second[1], "bottom")
        faces.append([bottom_first, bottom_second, top_second])
        faces.append([bottom_first, top_second, top_first])
        wall_segment_count += 1

    leaf_areas = np.asarray(
        [(leaf.row1 - leaf.row0) * (leaf.col1 - leaf.col0) for leaf in leaves],
        dtype=np.int64,
    )
    report = {
        "adaptive": True,
        "strategy": str(strategy),
        "coarse_cell_px": int(max(1, coarse_cell_px)),
        "leaf_count": len(leaves),
        "unit_leaf_count": int(np.count_nonzero(leaf_areas == 1)),
        "coarse_leaf_count": int(np.count_nonzero(leaf_areas > 1)),
        "wall_segment_count": int(wall_segment_count),
        "component_count": len(components),
        "uniform_grid_cell_count": int(footprint.sum()),
        "leaf_reduction_ratio": float(1.0 - len(leaves) / max(int(footprint.sum()), 1)),
        "feature_detection": feature_report,
    }
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64), report


def build_adaptive_relief_solid(
    heightmap,
    mask,
    width_mm,
    height_mm,
    base_thickness_mm,
    relief_height_mm,
    *,
    coarse_cell_px=4,
    gradient_threshold=0.035,
    curvature_threshold=0.025,
    feature_band_px=2,
):
    """Build one watertight solid while refining only feature-bearing cells."""
    values = np.asarray(heightmap, dtype=np.float32)
    footprint = np.asarray(mask, dtype=bool)
    if values.ndim != 2 or values.shape != footprint.shape or not values.size:
        raise ValueError("heightmap and mask must be matching non-empty 2D arrays")
    if not np.isfinite(values).all():
        raise ValueError("heightmap contains non-finite values")
    if not footprint.any():
        empty_vertices = np.zeros((0, 3), dtype=float)
        empty_faces = np.zeros((0, 3), dtype=np.int64)
        return empty_vertices, empty_faces, {"adaptive": True, "leaf_count": 0}
    if float(width_mm) <= 0.0 or float(height_mm) <= 0.0:
        raise ValueError("width_mm and height_mm must be positive")
    if float(base_thickness_mm) < 0.0 or float(relief_height_mm) < 0.0:
        raise ValueError("base and relief thickness must be non-negative")

    features, feature_report = detect_mesh_features(
        values,
        footprint,
        gradient_threshold=gradient_threshold,
        curvature_threshold=curvature_threshold,
        band_pixels=feature_band_px,
    )
    top_values = np.clip(values, 0.0, 1.0) * float(relief_height_mm)
    bottom_values = np.full(values.shape, -float(base_thickness_mm), dtype=np.float32)
    return _build_adaptive_continuous_surfaces(
        top_values,
        bottom_values,
        footprint,
        width_mm,
        height_mm,
        features,
        feature_report,
        coarse_cell_px,
        "feature_quadtree_with_conforming_hanging_edges",
    )


def build_adaptive_double_sided_relief_solid(
    front_heightmap,
    back_heightmap,
    mask,
    width_mm,
    height_mm,
    body_thickness_mm,
    front_relief_height_mm,
    back_relief_height_mm,
    *,
    coarse_cell_px=4,
    gradient_threshold=0.035,
    curvature_threshold=0.025,
    feature_band_px=2,
):
    """Build one adaptive fused body from front and back feature fields."""
    front = np.asarray(front_heightmap, dtype=np.float32)
    back = np.asarray(back_heightmap, dtype=np.float32)
    footprint = np.asarray(mask, dtype=bool)
    if front.ndim != 2 or front.shape != back.shape or front.shape != footprint.shape or not front.size:
        raise ValueError("front heightmap, back heightmap and mask must be matching non-empty 2D arrays")
    if not np.isfinite(front).all() or not np.isfinite(back).all():
        raise ValueError("double-side heightmaps contain non-finite values")
    if not footprint.any():
        return (
            np.zeros((0, 3), dtype=float),
            np.zeros((0, 3), dtype=np.int64),
            {"adaptive": True, "double_sided": True, "leaf_count": 0},
        )
    if float(width_mm) <= 0.0 or float(height_mm) <= 0.0 or float(body_thickness_mm) <= 0.0:
        raise ValueError("width_mm, height_mm and body_thickness_mm must be positive")
    if float(front_relief_height_mm) < 0.0 or float(back_relief_height_mm) < 0.0:
        raise ValueError("front and back relief thickness must be non-negative")

    front_features, front_report = detect_mesh_features(
        front,
        footprint,
        gradient_threshold=gradient_threshold,
        curvature_threshold=curvature_threshold,
        band_pixels=feature_band_px,
    )
    back_features, back_report = detect_mesh_features(
        back,
        footprint,
        gradient_threshold=gradient_threshold,
        curvature_threshold=curvature_threshold,
        band_pixels=feature_band_px,
    )
    features = front_features | back_features
    feature_report = {
        "front": front_report,
        "back": back_report,
        "union_refinement_band_pixel_count": int(features.sum()),
    }
    half_body = float(body_thickness_mm) / 2.0
    top_values = half_body + np.clip(front, 0.0, 1.0) * float(front_relief_height_mm)
    bottom_values = -half_body - np.clip(back, 0.0, 1.0) * float(back_relief_height_mm)
    vertices, faces, report = _build_adaptive_continuous_surfaces(
        top_values,
        bottom_values,
        footprint,
        width_mm,
        height_mm,
        features,
        feature_report,
        coarse_cell_px,
        "double_surface_feature_quadtree_with_conforming_hanging_edges",
    )
    report["double_sided"] = True
    return vertices, faces, report


def build_adaptive_layered_relief_solid(
    heightmap,
    mask,
    width_mm,
    height_mm,
    base_thickness_mm,
    relief_height_mm,
    *,
    coarse_cell_px=4,
    feature_band_px=2,
    max_levels=64,
):
    """Build exact discrete plateaus with feature-local adaptive XY density.

    Every adaptive leaf is a flat prism. Shared side intervals cancel in
    pairs; unmatched intervals become either the footprint wall or an exact
    vertical height step. Hanging edges are split by all neighbouring leaf
    corners, so coarse and fine leaves stay conforming.
    """
    values = np.asarray(heightmap, dtype=np.float32)
    footprint = np.asarray(mask, dtype=bool)
    if values.ndim != 2 or values.shape != footprint.shape or not values.size:
        raise ValueError("heightmap and mask must be matching non-empty 2D arrays")
    if not np.isfinite(values).all():
        raise ValueError("heightmap contains non-finite values")
    if not footprint.any():
        return (
            np.zeros((0, 3), dtype=float),
            np.zeros((0, 3), dtype=np.int64),
            {"adaptive": True, "exact_layers": True, "leaf_count": 0},
        )
    if float(width_mm) <= 0.0 or float(height_mm) <= 0.0:
        raise ValueError("width_mm and height_mm must be positive")
    if float(base_thickness_mm) < 0.0 or float(relief_height_mm) < 0.0:
        raise ValueError("base and relief thickness must be non-negative")
    normalized = np.clip(values, 0.0, 1.0)
    distinct_levels = np.unique(np.round(normalized[footprint], 9))
    if len(distinct_levels) > int(max_levels):
        raise ValueError(f"layered height mode supports at most {int(max_levels)} distinct height levels")

    features, feature_report = detect_mesh_features(
        normalized,
        footprint,
        gradient_threshold=1e-7,
        curvature_threshold=1e-7,
        band_pixels=feature_band_px,
    )
    labels, components = component_labels(footprint)
    leaves = _adaptive_leaves(
        footprint,
        features,
        labels,
        coarse_cell_px,
        discrete_values=normalized,
    )
    horizontal_points = defaultdict(set)
    vertical_points = defaultdict(set)
    for leaf in leaves:
        for row, col in (
            (leaf.row0, leaf.col0),
            (leaf.row0, leaf.col1),
            (leaf.row1, leaf.col0),
            (leaf.row1, leaf.col1),
        ):
            horizontal_points[row].add(col)
            vertical_points[col].add(row)

    foreground_rows, foreground_cols = np.nonzero(footprint)
    row_min, row_max = int(foreground_rows.min()), int(foreground_rows.max())
    col_min, col_max = int(foreground_cols.min()), int(foreground_cols.max())
    cell_width = float(width_mm) / float(col_max - col_min + 1)
    cell_height = float(height_mm) / float(row_max - row_min + 1)
    bottom_z = -float(base_thickness_mm)
    physical_levels = np.unique(
        np.concatenate(([bottom_z], distinct_levels.astype(float) * float(relief_height_mm)))
    )
    physical_levels.sort()
    vertices = []
    faces = []
    coordinate_vertices = {}
    side_intervals = defaultdict(list)

    def physical(row, col):
        return (float(col) - col_min) * cell_width, (float(row) - row_min) * cell_height

    def coordinate_vertex(component, row, col, z):
        key = (int(component), int(row), int(col), round(float(z), 9))
        index = coordinate_vertices.get(key)
        if index is None:
            x, y = physical(row, col)
            index = len(vertices)
            coordinate_vertices[key] = index
            vertices.append([x, y, float(z)])
        return index

    for leaf in leaves:
        perimeter = _leaf_perimeter(leaf, horizontal_points, vertical_points)
        if len(perimeter) < 4:
            continue
        local_values = normalized[leaf.row0 : leaf.row1, leaf.col0 : leaf.col1]
        local_mask = footprint[leaf.row0 : leaf.row1, leaf.col0 : leaf.col1]
        local_mean = float(np.mean(local_values[local_mask]))
        discrete_level = float(distinct_levels[int(np.argmin(np.abs(distinct_levels - local_mean)))])
        leaf_top = discrete_level * float(relief_height_mm)
        x_center, y_center = physical((leaf.row0 + leaf.row1) / 2.0, (leaf.col0 + leaf.col1) / 2.0)
        top_center = len(vertices)
        vertices.append([x_center, y_center, leaf_top])
        bottom_center = len(vertices)
        vertices.append([x_center, y_center, bottom_z])
        top_ring = [coordinate_vertex(leaf.component, row, col, leaf_top) for row, col in perimeter]
        bottom_ring = [coordinate_vertex(leaf.component, row, col, bottom_z) for row, col in perimeter]
        for index in range(len(perimeter)):
            next_index = (index + 1) % len(perimeter)
            faces.append([top_center, top_ring[index], top_ring[next_index]])
            faces.append([bottom_center, bottom_ring[next_index], bottom_ring[index]])
            first, second = perimeter[index], perimeter[next_index]
            for lower, upper in zip(physical_levels[:-1], physical_levels[1:]):
                if upper <= leaf_top + 1e-9:
                    key = (
                        leaf.component,
                        tuple(sorted((first, second))),
                        round(float(lower), 9),
                        round(float(upper), 9),
                    )
                    side_intervals[key].append((first, second, float(lower), float(upper)))

    wall_segment_count = 0
    cancelled_interval_count = 0
    overused_interval_count = 0
    for key, candidates in side_intervals.items():
        if len(candidates) == 2:
            cancelled_interval_count += 1
            continue
        if len(candidates) != 1:
            overused_interval_count += 1
            continue
        first, second, lower, upper = candidates[0]
        component = int(key[0])
        lower_first = coordinate_vertex(component, first[0], first[1], lower)
        lower_second = coordinate_vertex(component, second[0], second[1], lower)
        upper_first = coordinate_vertex(component, first[0], first[1], upper)
        upper_second = coordinate_vertex(component, second[0], second[1], upper)
        faces.append([lower_first, lower_second, upper_second])
        faces.append([lower_first, upper_second, upper_first])
        wall_segment_count += 1

    leaf_areas = np.asarray(
        [(leaf.row1 - leaf.row0) * (leaf.col1 - leaf.col0) for leaf in leaves],
        dtype=np.int64,
    )
    report = {
        "adaptive": True,
        "exact_layers": True,
        "strategy": "feature_quadtree_exact_layer_prisms",
        "coarse_cell_px": int(max(1, coarse_cell_px)),
        "leaf_count": len(leaves),
        "unit_leaf_count": int(np.count_nonzero(leaf_areas == 1)),
        "coarse_leaf_count": int(np.count_nonzero(leaf_areas > 1)),
        "wall_segment_count": int(wall_segment_count),
        "cancelled_internal_interval_count": int(cancelled_interval_count),
        "overused_interval_count": int(overused_interval_count),
        "component_count": len(components),
        "level_count": len(distinct_levels),
        "uniform_grid_cell_count": int(footprint.sum()),
        "leaf_reduction_ratio": float(1.0 - len(leaves) / max(int(footprint.sum()), 1)),
        "feature_detection": feature_report,
    }
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64), report
