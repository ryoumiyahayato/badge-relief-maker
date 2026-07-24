"""Global height processing and saved region-layer helpers."""

import numpy as np
from scipy import ndimage as ndi

from .height_markers import apply_manual_height_markers, manual_height_marker_region


def mean_filter(heightmap, mask=None):
    """Return a 3x3 mean without allowing void/background pixels to bleed in."""
    values = np.asarray(heightmap, dtype=float)
    if mask is None:
        weights = np.ones(values.shape, dtype=float)
    else:
        weights = np.asarray(mask, dtype=bool).astype(float)
        if weights.shape != values.shape:
            raise ValueError("heightmap and mask must have the same shape")
    padded_values = np.pad(values * weights, 1, mode="constant")
    padded_weights = np.pad(weights, 1, mode="constant")
    total = np.zeros_like(values)
    count = np.zeros_like(values)
    for row_offset in range(3):
        for col_offset in range(3):
            total += padded_values[row_offset : row_offset + values.shape[0], col_offset : col_offset + values.shape[1]]
            count += padded_weights[row_offset : row_offset + values.shape[0], col_offset : col_offset + values.shape[1]]
    return np.divide(total, np.maximum(count, 1.0))


def refine_heightmap(heightmap, mask, smooth_strength=0.0, detail_sharpness=0.0):
    values = np.asarray(heightmap, dtype=float).copy()
    foreground = np.asarray(mask, dtype=bool)
    smooth = float(np.clip(smooth_strength, 0.0, 1.0))
    sharp = float(np.clip(detail_sharpness, 0.0, 1.0))
    blurred = mean_filter(values, foreground)
    if smooth > 0.0:
        values[foreground] = values[foreground] * (1.0 - smooth) + blurred[foreground] * smooth
    if sharp > 0.0:
        reference = mean_filter(values, foreground)
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
        candidate, marker_report = apply_manual_height_markers(result, foreground, marker)
        if marker_report["applied_marker_count"]:
            feather_px = layer.get("feather_px")
            if feather_px is None and "feather_normalized" in layer:
                feather_px = float(layer.get("feather_normalized", 0.0)) * min(foreground.shape)
            try:
                feather_px = max(float(feather_px or 0.0), 0.0)
            except (TypeError, ValueError):
                feather_px = 0.0
            if feather_px > 0.0:
                distance = ndi.distance_transform_edt(region)
                weight = np.clip(distance / feather_px, 0.0, 1.0)
                result[region] = result[region] * (1.0 - weight[region]) + candidate[region] * weight[region]
            else:
                result = candidate
            applied += 1
            if bool(layer.get("locked", False)):
                locked |= region
    return result.astype(np.float32), locked, {
        "requested_layer_count": requested,
        "applied_layer_count": applied,
        "locked_pixel_count": int(locked.sum()),
    }
