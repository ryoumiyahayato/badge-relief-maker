"""Manual height marker helpers for local relief adjustment."""

import numpy as np


_SUPPORTED_MARKER_TYPES = {"height", "height_override", "set_height"}
_SUPPORTED_TARGETS = {"heightmap", "relief", "front", "back", "both"}


def apply_manual_height_markers(heightmap, mask, markers=()):
    """Apply circular manual height overrides to a normalized heightmap.

    Markers are dictionaries. Supported fields:
    - marker_type/type/kind: height, height_override or set_height.
    - target: front, back, both, heightmap or relief. Filtering by side is done
      by project_build; this helper only rejects unrelated target values.
    - x, y: normalized coordinates by default, or pixel coordinates when
      coordinate_space is pixel/pixels.
    - height_normalized/normalized_height/value/height: target height in 0..1.
    - radius_px or radius_normalized: circular edit radius.
    """
    heightmap = np.asarray(heightmap, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if heightmap.shape != mask.shape:
        raise ValueError("heightmap and mask must have the same shape")
    if heightmap.ndim != 2:
        raise ValueError("heightmap must be a 2D array")

    result = heightmap.copy()
    marker_list = list(markers or [])
    report = {
        "enabled": False,
        "requested_marker_count": int(len(marker_list)),
        "applied_marker_count": 0,
        "ignored_marker_count": 0,
        "affected_pixel_count": 0,
    }

    if not marker_list or not mask.any():
        return result, report

    affected_total = np.zeros(mask.shape, dtype=bool)
    rows, cols = mask.shape
    for marker in marker_list:
        if not isinstance(marker, dict):
            report["ignored_marker_count"] += 1
            continue
        normalized = _normalize_marker(marker)
        if normalized is None:
            report["ignored_marker_count"] += 1
            continue

        cx, cy, radius_px, height = normalized
        yy, xx = np.ogrid[:rows, :cols]
        region = ((xx - cx) ** 2 + (yy - cy) ** 2 <= radius_px**2) & mask
        if not region.any():
            report["ignored_marker_count"] += 1
            continue
        result[region] = height
        affected_total |= region
        report["applied_marker_count"] += 1

    report["affected_pixel_count"] = int(affected_total.sum())
    report["enabled"] = bool(report["applied_marker_count"] > 0)
    return result, report


def _normalize_marker(marker):
    marker_type = str(marker.get("marker_type", marker.get("type", marker.get("kind", "height")))).lower()
    if marker_type not in _SUPPORTED_MARKER_TYPES:
        return None

    target = str(marker.get("target", "heightmap")).lower()
    if target not in _SUPPORTED_TARGETS:
        return None

    x = _float_or_none(marker.get("x", marker.get("center_x")))
    y = _float_or_none(marker.get("y", marker.get("center_y")))
    if x is None or y is None:
        return None

    height = _height_value(marker)
    if height is None:
        return None

    coordinate_space = str(marker.get("coordinate_space", marker.get("space", "normalized"))).lower()
    shape = marker.get("shape", None)
    if coordinate_space in {"pixel", "pixels", "image_pixel"}:
        cx = x
        cy = y
    else:
        if shape is not None and len(shape) == 2:
            rows, cols = int(shape[0]), int(shape[1])
        else:
            rows, cols = 1, 1
        cx = x * max(cols - 1, 1)
        cy = y * max(rows - 1, 1)

    radius_px = _radius_px(marker)
    if radius_px is None or radius_px < 0.0:
        return None
    return float(cx), float(cy), float(radius_px), float(height)


def _height_value(marker):
    for key in ["height_normalized", "normalized_height", "value", "height"]:
        if key in marker:
            value = _float_or_none(marker.get(key))
            if value is None:
                return None
            return _clamp01(value)
    return None


def _radius_px(marker):
    if "radius_px" in marker:
        value = _float_or_none(marker.get("radius_px"))
        if value is None:
            return None
        return value
    if "radius" in marker:
        value = _float_or_none(marker.get("radius"))
        if value is None:
            return None
        return value
    if "radius_normalized" in marker:
        value = _float_or_none(marker.get("radius_normalized"))
        if value is None:
            return None
        shape = marker.get("shape", None)
        if shape is not None and len(shape) == 2:
            return value * min(int(shape[0]), int(shape[1]))
        return value
    return 0.0


def _float_or_none(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(result):
        return None
    return result


def _clamp01(value):
    return float(min(max(float(value), 0.0), 1.0))
