"""Manual height marker helpers for local relief adjustment."""

import numpy as np


_SUPPORTED_MARKER_TYPES = {"height", "height_override", "set_height"}
_SUPPORTED_TARGETS = {"heightmap", "relief", "front", "back", "both"}
_SET_OPERATIONS = {"set", "replace", "override", "height_override", "set_height"}
_ADD_OPERATIONS = {"add", "raise", "increase"}
_SUBTRACT_OPERATIONS = {"subtract", "sub", "lower", "decrease"}


def apply_manual_height_markers(heightmap, mask, markers=()):
    """Apply manual height edits to a normalized heightmap.

    Markers are dictionaries. Supported fields:
    - marker_type/type/kind: height, height_override or set_height.
    - target: front, back, both, heightmap or relief. Filtering by side is done
      by project_build; this helper only rejects unrelated target values.
    - shape: circle/brush or rectangle/rect/box.
    - x, y: normalized coordinates by default, or pixel coordinates when
      coordinate_space is pixel/pixels.
    - height_normalized/normalized_height/value/height: target height in 0..1.
    - delta/delta_height: additive height change for add/subtract operations.
    - operation/mode: set, add or subtract.
    - radius_px or radius_normalized: circular edit radius.
    - width_px/height_px or width_normalized/height_normalized: rectangle size.
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
    for marker in marker_list:
        if not isinstance(marker, dict):
            report["ignored_marker_count"] += 1
            continue
        normalized = _normalize_marker(marker, mask.shape)
        if normalized is None:
            report["ignored_marker_count"] += 1
            continue

        region = _marker_region(mask, normalized)
        if not region.any():
            report["ignored_marker_count"] += 1
            continue
        result[region] = _apply_operation(result[region], normalized)
        affected_total |= region
        report["applied_marker_count"] += 1

    report["affected_pixel_count"] = int(affected_total.sum())
    report["enabled"] = bool(report["applied_marker_count"] > 0)
    return result, report


def _normalize_marker(marker, default_shape):
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

    coordinate_space = str(marker.get("coordinate_space", marker.get("space", "normalized"))).lower()
    shape = marker.get("shape", default_shape)
    rows, cols = int(shape[0]), int(shape[1]) if _looks_like_shape(shape) else (int(default_shape[0]), int(default_shape[1]))
    if coordinate_space in {"pixel", "pixels", "image_pixel"}:
        cx = x
        cy = y
    else:
        cx = x * max(cols - 1, 1)
        cy = y * max(rows - 1, 1)

    operation = _operation(marker)
    value = _operation_value(marker, operation)
    if value is None:
        return None

    marker_shape = str(marker.get("shape_type", marker.get("brush_shape", marker.get("region_shape", "circle")))).lower()
    if marker_shape in {"rectangle", "rect", "box"}:
        width_px, height_px = _rectangle_size_px(marker, default_shape)
        if width_px is None or height_px is None or width_px < 0.0 or height_px < 0.0:
            return None
        return {
            "shape": "rectangle",
            "cx": float(cx),
            "cy": float(cy),
            "width_px": float(width_px),
            "height_px": float(height_px),
            "operation": operation,
            "value": float(value),
        }

    radius_px = _radius_px(marker, default_shape)
    if radius_px is None or radius_px < 0.0:
        return None
    return {
        "shape": "circle",
        "cx": float(cx),
        "cy": float(cy),
        "radius_px": float(radius_px),
        "operation": operation,
        "value": float(value),
    }


def _looks_like_shape(value):
    try:
        return len(value) == 2
    except TypeError:
        return False


def _marker_region(mask, marker):
    rows, cols = mask.shape
    yy, xx = np.ogrid[:rows, :cols]
    if marker["shape"] == "rectangle":
        half_w = marker["width_px"] / 2.0
        half_h = marker["height_px"] / 2.0
        region = (np.abs(xx - marker["cx"]) <= half_w) & (np.abs(yy - marker["cy"]) <= half_h)
    else:
        region = (xx - marker["cx"]) ** 2 + (yy - marker["cy"]) ** 2 <= marker["radius_px"] ** 2
    return region & mask


def _apply_operation(values, marker):
    operation = marker["operation"]
    value = marker["value"]
    if operation == "add":
        return np.clip(values + value, 0.0, 1.0)
    if operation == "subtract":
        return np.clip(values - value, 0.0, 1.0)
    return np.full_like(values, value, dtype=float)


def _operation(marker):
    raw = str(marker.get("operation", marker.get("mode", "set"))).lower()
    if raw in _ADD_OPERATIONS:
        return "add"
    if raw in _SUBTRACT_OPERATIONS:
        return "subtract"
    if raw in _SET_OPERATIONS:
        return "set"
    return "set"


def _operation_value(marker, operation):
    if operation in {"add", "subtract"}:
        for key in ["delta", "delta_height", "height_delta", "value", "height"]:
            if key in marker:
                value = _float_or_none(marker.get(key))
                if value is None:
                    return None
                return _clamp01(abs(value))
        return None
    return _height_value(marker)


def _height_value(marker):
    for key in ["height_normalized", "normalized_height", "value", "height"]:
        if key in marker:
            value = _float_or_none(marker.get(key))
            if value is None:
                return None
            return _clamp01(value)
    return None


def _radius_px(marker, default_shape):
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
        shape = marker.get("shape", default_shape)
        if not _looks_like_shape(shape):
            shape = default_shape
        return value * min(int(shape[0]), int(shape[1]))
    return 0.0


def _rectangle_size_px(marker, default_shape):
    width = _dimension_px(marker, "width", default_shape)
    height = _dimension_px(marker, "height", default_shape)
    if width is None and "size_px" in marker:
        width = _float_or_none(marker.get("size_px"))
    if height is None and "size_px" in marker:
        height = _float_or_none(marker.get("size_px"))
    return width, height


def _dimension_px(marker, prefix, default_shape):
    pixel_key = f"{prefix}_px"
    normalized_key = f"{prefix}_normalized"
    if pixel_key in marker:
        return _float_or_none(marker.get(pixel_key))
    if normalized_key in marker:
        value = _float_or_none(marker.get(normalized_key))
        if value is None:
            return None
        shape = marker.get("shape", default_shape)
        if not _looks_like_shape(shape):
            shape = default_shape
        axis = int(shape[1]) if prefix == "width" else int(shape[0])
        return value * max(axis - 1, 1)
    return None


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
