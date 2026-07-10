"""Global height processing and saved region-layer helpers."""

import numpy as np

from .height_markers import apply_manual_height_markers, manual_height_marker_region


def mean_filter(heightmap):
    values = np.asarray(heightmap, dtype=float)
    padded = np.pad(values, 1, mode="edge")
    total = np.zeros_like(values)
    for row_offset in range(3):
        for col_offset in range(3):
            total += padded[row_offset : row_offset + values.shape[0], col_offset : col_offset + values.shape[1]]
    return total / 9.0


def refine_heightmap(heightmap, mask, smooth_strength=0.0, detail_sharpness=0.0):
    values = np.asarray(heightmap, dtype=float).copy()
    foreground = np.asarray(mask, dtype=bool)
    smooth = float(np.clip(smooth_strength, 0.0, 1.0))
    sharp = float(np.clip(detail_sharpness, 0.0, 1.0))
    blurred = mean_filter(values)
    if smooth > 0.0:
        values[foreground] = values[foreground] * (1.0 - smooth) + blurred[foreground] * smooth
    if sharp > 0.0:
        reference = mean_filter(values)
        values[foreground] = values[foreground] + sharp * (values[foreground] - reference[foreground])
    values = np.where(foreground, np.clip(values, 0.0, 1.0), 0.0)
    return values.astype(np.float32), {"smooth_strength": smooth, "detail_sharpness": sharp}


def apply_region_layers(heightmap, mask, layers=()):
    """Apply ordered marker-shaped layers and return a lock mask."""
    result = np.asarray(heightmap, dtype=float).copy()
    foreground = np.asarray(mask, dtype=bool)
    locked = np.zeros(foreground.shape, dtype=bool)
    requested = 0
    applied = 0
    for layer in layers or ():
        requested += 1
        if not isinstance(layer, dict):
            continue
        marker = dict(layer)
        marker.setdefault("operation", "set")
        if not any(key in marker for key in ("height_normalized", "normalized_height", "height", "value")):
            continue
        region = manual_height_marker_region(foreground, marker)
        if not region.any():
            continue
        result, marker_report = apply_manual_height_markers(result, foreground, marker)
        if marker_report["applied_marker_count"]:
            applied += 1
            if bool(layer.get("locked", False)):
                locked |= region
    return result.astype(np.float32), locked, {
        "requested_layer_count": requested,
        "applied_layer_count": applied,
        "locked_pixel_count": int(locked.sum()),
    }
