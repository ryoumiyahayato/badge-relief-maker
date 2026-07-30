"""Front/back alignment and fused double-side relief construction."""

import numpy as np
from PIL import Image

from .components import connected_components
from .masked_solid_builder import build_double_sided_relief_solid
from .options import FOOTPRINT_MODES


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
    # Pillow's affine/resize path can clamp ``I;16`` values to 8-bit range.
    # Keep normalized relief values in floating-point mode throughout alignment.
    height_image = Image.fromarray(np.clip(np.asarray(heightmap, dtype=np.float32), 0.0, 1.0), mode="F")
    resized_mask = np.asarray(mask_image.resize((cols, rows), Image.Resampling.NEAREST)) > 0
    resized_height = np.asarray(height_image.resize((cols, rows), Image.Resampling.BILINEAR), dtype=np.float32)
    return resized_mask, np.where(resized_mask, resized_height, 0.0).astype(np.float32)


def _affine_back(mask, heightmap, width_mm, height_mm, scale, rotation_deg, offset_x_mm, offset_y_mm, flip_horizontal):
    source_mask = np.asarray(mask, dtype=bool)
    source_height = np.clip(np.asarray(heightmap, dtype=np.float32), 0.0, 1.0)
    if flip_horizontal:
        source_mask = np.fliplr(source_mask)
        source_height = np.fliplr(source_height)

    rows, cols = source_mask.shape
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
    yy, xx = np.mgrid[:rows, :cols]
    output_x = xx - center_x - offset_x
    output_y = yy - center_y - offset_y
    source_x = (cosine * output_x + sine * output_y) / scale + center_x
    source_y = (-sine * output_x + cosine * output_y) / scale + center_y

    nearest_x = np.floor(source_x + 0.5).astype(int)
    nearest_y = np.floor(source_y + 0.5).astype(int)
    nearest_valid = (nearest_x >= 0) & (nearest_x < cols) & (nearest_y >= 0) & (nearest_y < rows)
    result_mask = np.zeros((rows, cols), dtype=bool)
    result_mask[nearest_valid] = source_mask[nearest_y[nearest_valid], nearest_x[nearest_valid]]

    sample_valid = (source_x >= 0.0) & (source_x <= cols - 1.0) & (source_y >= 0.0) & (source_y <= rows - 1.0)
    x0 = np.clip(np.floor(source_x).astype(int), 0, cols - 1)
    y0 = np.clip(np.floor(source_y).astype(int), 0, rows - 1)
    x1 = np.minimum(x0 + 1, cols - 1)
    y1 = np.minimum(y0 + 1, rows - 1)
    wx = source_x - x0
    wy = source_y - y0
    result_height = (
        source_height[y0, x0] * (1.0 - wx) * (1.0 - wy)
        + source_height[y0, x1] * wx * (1.0 - wy)
        + source_height[y1, x0] * (1.0 - wx) * wy
        + source_height[y1, x1] * wx * wy
    ).astype(np.float32)
    result_height[~sample_valid] = 0.0
    return result_mask, np.where(result_mask, result_height, 0.0).astype(np.float32)


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
    mode = str(footprint_mode or FOOTPRINT_MODES.default).lower()
    if mode not in FOOTPRINT_MODES:
        raise ValueError("double-side footprint_mode must be union, intersection, front or back")
    if mode == "intersection":
        footprint = front_mask & back_mask
    elif mode == "front":
        footprint = front_mask.copy()
    elif mode == "back":
        footprint = back_mask.copy()
    else:
        footprint = front_mask | back_mask
    if not footprint.any():
        raise ValueError("aligned front/back masks have no shared production footprint")
    front_heightmap = np.where(front_mask & footprint, front_heightmap, 0.0)
    back_heightmap = np.where(back_mask & footprint, back_heightmap, 0.0)
    return footprint, front_heightmap, back_heightmap, {
        "grid_shape": list(shape),
        "footprint_mode": mode,
        "footprint_component_count": len(connected_components(footprint)),
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
