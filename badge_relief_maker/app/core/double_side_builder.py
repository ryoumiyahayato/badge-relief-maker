"""Front/back alignment and fused double-side relief construction."""

from collections import deque

import numpy as np
from PIL import Image

from .masked_solid_builder import build_double_sided_relief_solid


def common_grid_shape(width_mm, height_mm, max_cells):
    width = float(width_mm)
    height = float(height_mm)
    cells = max(4, int(max_cells))
    cols = max(2, int(round(np.sqrt(cells * width / height))))
    rows = max(2, int(cells // cols))
    return rows, cols


def _resize_field(mask, heightmap, shape):
    rows, cols = shape
    mask_image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    height_image = Image.fromarray(np.clip(np.asarray(heightmap) * 65535.0, 0, 65535).astype(np.uint16))
    resized_mask = np.asarray(mask_image.resize((cols, rows), Image.Resampling.NEAREST)) > 0
    resized_height = np.asarray(height_image.resize((cols, rows), Image.Resampling.BILINEAR)).astype(np.float32) / 65535.0
    return resized_mask, np.where(resized_mask, resized_height, 0.0).astype(np.float32)


def _affine_back(mask, heightmap, width_mm, height_mm, scale, rotation_deg, offset_x_mm, offset_y_mm, flip_horizontal):
    rows, cols = mask.shape
    mask_image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    height_image = Image.fromarray(np.clip(heightmap * 65535.0, 0, 65535).astype(np.uint16))
    if flip_horizontal:
        mask_image = mask_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        height_image = height_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    scale = float(scale)
    if not np.isfinite(scale) or scale <= 0.0:
        raise ValueError("double-side back_scale must be positive and finite")
    rotation = np.deg2rad(float(rotation_deg))
    cosine = float(np.cos(rotation))
    sine = float(np.sin(rotation))
    center_x = (cols - 1.0) / 2.0
    center_y = (rows - 1.0) / 2.0
    offset_x = float(offset_x_mm) / float(width_mm) * cols
    offset_y = float(offset_y_mm) / float(height_mm) * rows
    inverse_scale = 1.0 / scale
    a = cosine * inverse_scale
    b = sine * inverse_scale
    d = -sine * inverse_scale
    e = cosine * inverse_scale
    c = center_x - a * (center_x + offset_x) - b * (center_y + offset_y)
    f = center_y - d * (center_x + offset_x) - e * (center_y + offset_y)
    coefficients = (a, b, c, d, e, f)
    transformed_mask = mask_image.transform(
        (cols, rows),
        Image.Transform.AFFINE,
        coefficients,
        resample=Image.Resampling.NEAREST,
        fillcolor=0,
    )
    transformed_height = height_image.transform(
        (cols, rows),
        Image.Transform.AFFINE,
        coefficients,
        resample=Image.Resampling.BILINEAR,
        fillcolor=0,
    )
    result_mask = np.asarray(transformed_mask) > 0
    result_height = np.asarray(transformed_height).astype(np.float32) / 65535.0
    return result_mask, np.where(result_mask, result_height, 0.0).astype(np.float32)


def _component_count(mask):
    mask = np.asarray(mask, dtype=bool)
    visited = np.zeros(mask.shape, dtype=bool)
    count = 0
    rows, cols = mask.shape
    for start_row, start_col in zip(*np.nonzero(mask)):
        if visited[start_row, start_col]:
            continue
        count += 1
        visited[start_row, start_col] = True
        queue = deque([(int(start_row), int(start_col))])
        while queue:
            row, col = queue.popleft()
            for next_row, next_col in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if 0 <= next_row < rows and 0 <= next_col < cols and mask[next_row, next_col] and not visited[next_row, next_col]:
                    visited[next_row, next_col] = True
                    queue.append((next_row, next_col))
    return count


def align_relief_fields(
    front_mask,
    front_heightmap,
    back_mask,
    back_heightmap,
    width_mm,
    height_mm,
    max_grid_cells,
    back_scale=1.0,
    back_rotation_deg=0.0,
    back_offset_x_mm=0.0,
    back_offset_y_mm=0.0,
    flip_back_horizontal=True,
    footprint_mode="union",
):
    """Resample and manually align two viewed-face relief fields."""
    shape = common_grid_shape(width_mm, height_mm, max_grid_cells)
    front_mask, front_heightmap = _resize_field(front_mask, front_heightmap, shape)
    back_mask, back_heightmap = _resize_field(back_mask, back_heightmap, shape)
    back_mask, back_heightmap = _affine_back(
        back_mask,
        back_heightmap,
        width_mm,
        height_mm,
        back_scale,
        back_rotation_deg,
        back_offset_x_mm,
        back_offset_y_mm,
        flip_back_horizontal,
    )
    mode = str(footprint_mode or "union").lower()
    if mode == "intersection":
        footprint = front_mask & back_mask
    elif mode == "front":
        footprint = front_mask.copy()
    elif mode == "back":
        footprint = back_mask.copy()
    elif mode == "union":
        footprint = front_mask | back_mask
    else:
        raise ValueError("double-side footprint_mode must be union, intersection, front or back")
    if not footprint.any():
        raise ValueError("aligned front/back masks have no shared production footprint")
    front_heightmap = np.where(front_mask & footprint, front_heightmap, 0.0)
    back_heightmap = np.where(back_mask & footprint, back_heightmap, 0.0)
    return footprint, front_heightmap, back_heightmap, {
        "grid_shape": list(shape),
        "footprint_mode": mode,
        "footprint_component_count": _component_count(footprint),
        "back_scale": float(back_scale),
        "back_rotation_deg": float(back_rotation_deg),
        "back_offset_mm_xy": [float(back_offset_x_mm), float(back_offset_y_mm)],
        "flip_back_horizontal": bool(flip_back_horizontal),
    }


def build_fused_double_sided_relief(
    front_mask,
    front_heightmap,
    back_mask,
    back_heightmap,
    width_mm,
    height_mm,
    body_thickness_mm,
    front_relief_height_mm,
    back_relief_height_mm,
    max_grid_cells,
    alignment=None,
    edge_style="straight",
    bevel_mm=0.0,
    radius_mm=0.0,
):
    alignment = alignment or {}
    footprint, front_field, back_field, report = align_relief_fields(
        front_mask,
        front_heightmap,
        back_mask,
        back_heightmap,
        width_mm,
        height_mm,
        max_grid_cells,
        back_scale=alignment.get("back_scale", 1.0),
        back_rotation_deg=alignment.get("back_rotation_deg", 0.0),
        back_offset_x_mm=alignment.get("back_offset_x_mm", 0.0),
        back_offset_y_mm=alignment.get("back_offset_y_mm", 0.0),
        flip_back_horizontal=alignment.get("flip_back_horizontal", True),
        footprint_mode=alignment.get("footprint_mode", "union"),
    )
    if report["footprint_component_count"] != 1:
        raise ValueError("fused double-side production mode requires one connected aligned footprint")
    vertices, faces = build_double_sided_relief_solid(
        front_field,
        back_field,
        footprint,
        width_mm,
        height_mm,
        body_thickness_mm,
        front_relief_height_mm,
        back_relief_height_mm,
        edge_style=edge_style,
        bevel_mm=bevel_mm,
        radius_mm=radius_mm,
    )
    return vertices, faces, footprint, front_field, back_field, report


def align_placeholder(front_heightmap, back_heightmap):
    """Backward-compatible exact-shape alignment helper."""
    if front_heightmap.shape != back_heightmap.shape:
        raise ValueError("front and back heightmaps must have the same shape")
    return front_heightmap, back_heightmap
