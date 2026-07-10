"""Manual height marker helpers for local relief adjustment."""

import numpy as np


_SUPPORTED_MARKER_TYPES = {"height", "height_override", "set_height"}
_SUPPORTED_TARGETS = {"heightmap", "relief", "front", "back", "both"}
_SET_OPERATIONS = {"set", "replace", "override", "height_override", "set_height"}
_ADD_OPERATIONS = {"add", "raise", "increase"}
_SUBTRACT_OPERATIONS = {"subtract", "sub", "lower", "decrease"}
_SMOOTH_OPERATIONS = {"smooth", "soften", "blur"}
_POLYGON_SHAPES = {"polygon", "poly", "freeform", "free_form"}
_RECTANGLE_SHAPES = {"rectangle", "rect", "box"}


def apply_manual_height_markers(heightmap, mask, markers=()):
    """Apply manual height edits to a normalized heightmap.

    Markers may be one dictionary or an iterable of dictionaries. Supported fields:
    - marker_type/type/kind: height, height_override or set_height.
    - target: front, back, both, heightmap or relief. Filtering by side is done
      by project_build; this helper only rejects unrelated target values.
    - shape/shape_type/brush_shape/region_shape: circle/brush, rectangle/rect/box
      or polygon/poly/freeform.
    - x, y: normalized coordinates by default, or pixel coordinates when
      coordinate_space is pixel/pixels. Required for circle and rectangle.
    - points/vertices/polygon_points: polygon points for polygon markers.
    - height_normalized/normalized_height/value/height: target height in 0..1.
    - delta/delta_height: additive height change for add/subtract operations.
    - operation/mode: set, add or subtract.
    - radius_px or radius_normalized: circular edit radius.
    - width_px/height_px, width_normalized and rect/region normalized dimensions.
    """
    heightmap = np.asarray(heightmap, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if heightmap.shape != mask.shape:
        raise ValueError("heightmap and mask must have the same shape")
    if heightmap.ndim != 2:
        raise ValueError("heightmap must be a 2D array")

    result = heightmap.copy()
    marker_list = _marker_list(markers)
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
        normalized = normalize_manual_height_marker(marker, mask.shape)
        if normalized is None:
            report["ignored_marker_count"] += 1
            continue

        region = _marker_region(mask, normalized)
        if not region.any():
            report["ignored_marker_count"] += 1
            continue
        if normalized["operation"] == "smooth":
            blurred = _mean_filter_3x3(result)
            strength = normalized["value"]
            result[region] = result[region] * (1.0 - strength) + blurred[region] * strength
        else:
            result[region] = _apply_operation(result[region], normalized)
        affected_total |= region
        report["applied_marker_count"] += 1

    report["affected_pixel_count"] = int(affected_total.sum())
    report["enabled"] = bool(report["applied_marker_count"] > 0)
    return result, report


def normalize_manual_height_marker(marker, grid_shape):
    """Validate and normalize one marker for a processed heightmap grid."""
    if not isinstance(marker, dict):
        return None
    return _normalize_marker(marker, grid_shape)


def manual_height_marker_region(mask, marker):
    """Return the clipped boolean region selected by one marker."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")
    normalized = _normalize_marker(marker, mask.shape) if isinstance(marker, dict) else None
    if normalized is None:
        return np.zeros(mask.shape, dtype=bool)
    return _marker_region(mask, normalized)


def _marker_list(markers):
    if markers is None:
        return []
    if isinstance(markers, dict):
        return [markers]
    if isinstance(markers, (str, bytes)):
        return [markers]
    try:
        return list(markers)
    except TypeError:
        return [markers]


def _normalize_marker(marker, default_shape):
    marker_type = str(marker.get("marker_type", marker.get("type", marker.get("kind", "height")))).lower()
    if marker_type not in _SUPPORTED_MARKER_TYPES:
        return None

    target = str(marker.get("target", "heightmap")).lower()
    if target not in _SUPPORTED_TARGETS:
        return None

    operation = _operation(marker)
    value = _operation_value(marker, operation)
    if value is None:
        return None

    marker_shape = _marker_shape(marker)
    if marker_shape in _POLYGON_SHAPES:
        points = _polygon_points_px(marker, default_shape)
        if points is None:
            return None
        return {
            "shape": "polygon",
            "points": points,
            "operation": operation,
            "value": float(value),
        }

    x = _float_or_none(marker.get("x", marker.get("center_x")))
    y = _float_or_none(marker.get("y", marker.get("center_y")))
    if x is None or y is None:
        return None

    coordinate_space = str(marker.get("coordinate_space", marker.get("space", "normalized"))).lower()
    rows, cols = _grid_shape(marker, default_shape)
    if coordinate_space in {"pixel", "pixels", "image_pixel"}:
        cx = x
        cy = y
    else:
        cx = x * max(cols - 1, 1)
        cy = y * max(rows - 1, 1)

    if marker_shape in _RECTANGLE_SHAPES:
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


def _grid_shape(marker, default_shape):
    for key in ["grid_shape", "heightmap_shape", "image_shape", "mask_shape"]:
        if _looks_like_shape(marker.get(key)):
            value = marker.get(key)
            return int(value[0]), int(value[1])
    shape_value = marker.get("shape")
    if _looks_like_shape(shape_value):
        return int(shape_value[0]), int(shape_value[1])
    return int(default_shape[0]), int(default_shape[1])


def _marker_shape(marker):
    for key in ["shape", "shape_type", "brush_shape", "region_shape"]:
        value = marker.get(key)
        if isinstance(value, str):
            return value.lower()
    return "circle"


def _looks_like_shape(value):
    try:
        if len(value) != 2:
            return False
        int(value[0])
        int(value[1])
        return True
    except (TypeError, ValueError):
        return False


def _marker_region(mask, marker):
    rows, cols = mask.shape
    yy, xx = np.ogrid[:rows, :cols]
    if marker["shape"] == "rectangle":
        half_w = marker["width_px"] / 2.0
        half_h = marker["height_px"] / 2.0
        region = (np.abs(xx - marker["cx"]) <= half_w) & (np.abs(yy - marker["cy"]) <= half_h)
    elif marker["shape"] == "polygon":
        region = _polygon_region(rows, cols, marker["points"])
    else:
        region = (xx - marker["cx"]) ** 2 + (yy - marker["cy"]) ** 2 <= marker["radius_px"] ** 2
    return region & mask


def _polygon_region(rows, cols, points):
    yy, xx = np.mgrid[:rows, :cols]
    inside = np.zeros((rows, cols), dtype=bool)
    x_points = points[:, 0]
    y_points = points[:, 1]
    count = len(points)
    for index in range(count):
        next_index = (index + 1) % count
        x1, y1 = x_points[index], y_points[index]
        x2, y2 = x_points[next_index], y_points[next_index]
        crosses = (y1 > yy) != (y2 > yy)
        x_at_y = (x2 - x1) * (yy - y1) / ((y2 - y1) if y2 != y1 else 1e-12) + x1
        inside ^= crosses & (xx < x_at_y)
    return inside


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
    if raw in _SMOOTH_OPERATIONS:
        return "smooth"
    if raw in _SET_OPERATIONS:
        return "set"
    return "set"


def _operation_value(marker, operation):
    if operation == "smooth":
        value = _float_or_none(marker.get("strength", marker.get("value", 1.0)))
        return None if value is None else _clamp01(value)
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
        rows, cols = _grid_shape(marker, default_shape)
        return value * min(rows, cols)
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
    for key in _dimension_keys(prefix, normalized=False):
        if key in marker:
            return _float_or_none(marker.get(key))
    for key in _dimension_keys(prefix, normalized=True):
        if key in marker:
            value = _float_or_none(marker.get(key))
            if value is None:
                return None
            rows, cols = _grid_shape(marker, default_shape)
            axis = cols if prefix == "width" else rows
            return value * max(axis - 1, 1)
    return None


def _dimension_keys(prefix, normalized):
    suffix = "normalized" if normalized else "px"
    if prefix == "width":
        return [f"width_{suffix}", f"rect_width_{suffix}", f"region_width_{suffix}", f"box_width_{suffix}"]
    return [f"height_{suffix}", f"rect_height_{suffix}", f"region_height_{suffix}", f"box_height_{suffix}"] if not normalized else [
        "rect_height_normalized",
        "region_height_normalized",
        "box_height_normalized",
        "height_size_normalized",
    ]


def _polygon_points_px(marker, default_shape):
    points = marker.get("points", marker.get("vertices", marker.get("polygon_points")))
    try:
        points = list(points)
    except TypeError:
        return None
    if len(points) < 3:
        return None

    coordinate_space = str(marker.get("coordinate_space", marker.get("space", "normalized"))).lower()
    rows, cols = _grid_shape(marker, default_shape)
    result = []
    for point in points:
        if isinstance(point, dict):
            x = _float_or_none(point.get("x"))
            y = _float_or_none(point.get("y"))
        else:
            try:
                x = _float_or_none(point[0])
                y = _float_or_none(point[1])
            except (TypeError, IndexError):
                return None
        if x is None or y is None:
            return None
        if coordinate_space not in {"pixel", "pixels", "image_pixel"}:
            x = x * max(cols - 1, 1)
            y = y * max(rows - 1, 1)
        result.append((float(x), float(y)))
    return np.asarray(result, dtype=float)


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


def _mean_filter_3x3(values):
    padded = np.pad(np.asarray(values, dtype=float), 1, mode="edge")
    total = np.zeros_like(values, dtype=float)
    for row_offset in range(3):
        for col_offset in range(3):
            total += padded[row_offset : row_offset + values.shape[0], col_offset : col_offset + values.shape[1]]
    return total / 9.0
