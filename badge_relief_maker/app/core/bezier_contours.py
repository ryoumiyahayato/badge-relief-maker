"""Editable cubic Bezier contours for persistent footprint correction."""

import math

import numpy as np
from PIL import Image, ImageDraw

from .options import CONTOUR_OPERATIONS
from .outline_extractor import boundary_edges_from_mask, simplify_collinear_points, trace_boundary_loops


def _point(value):
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (np.isfinite(x) and np.isfinite(y)):
        return None
    return [float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))]


def normalize_bezier_contour(contour):
    """Return one safe normalized contour or ``None``."""
    if not isinstance(contour, dict):
        return None
    operation = str(contour.get("operation", CONTOUR_OPERATIONS.default)).strip().lower()
    if operation not in CONTOUR_OPERATIONS:
        return None
    points = []
    for raw in contour.get("points", []):
        if not isinstance(raw, dict):
            return None
        anchor = _point(raw.get("anchor"))
        handle_in = _point(raw.get("in", anchor))
        handle_out = _point(raw.get("out", anchor))
        if anchor is None or handle_in is None or handle_out is None:
            return None
        points.append({"anchor": anchor, "in": handle_in, "out": handle_out})
    if len(points) < 3:
        return None
    return {
        "operation": operation,
        "closed": bool(contour.get("closed", True)),
        "points": points,
        "contour_id": str(contour.get("contour_id", "")),
    }


def cubic_point(start, control_one, control_two, end, t):
    """Evaluate one cubic Bezier segment."""
    t = float(t)
    inverse = 1.0 - t
    return (
        inverse**3 * np.asarray(start, dtype=float)
        + 3.0 * inverse**2 * t * np.asarray(control_one, dtype=float)
        + 3.0 * inverse * t**2 * np.asarray(control_two, dtype=float)
        + t**3 * np.asarray(end, dtype=float)
    )


def sample_bezier_contour(contour, samples_per_segment=24):
    """Sample one contour into a normalized polygon."""
    normalized = normalize_bezier_contour(contour)
    if normalized is None:
        return np.zeros((0, 2), dtype=float)
    points = normalized["points"]
    segment_count = len(points) if normalized["closed"] else len(points) - 1
    sampled = []
    samples = max(4, int(samples_per_segment))
    for index in range(segment_count):
        current = points[index]
        following = points[(index + 1) % len(points)]
        for sample_index in range(samples):
            sampled.append(
                cubic_point(
                    current["anchor"],
                    current["out"],
                    following["in"],
                    following["anchor"],
                    sample_index / samples,
                )
            )
    if sampled and normalized["closed"]:
        sampled.append(np.asarray(sampled[0], dtype=float))
    return np.asarray(sampled, dtype=float)


def rasterize_bezier_contour(contour, shape, samples_per_segment=24):
    """Rasterize one normalized closed contour into a boolean image mask."""
    rows, cols = int(shape[0]), int(shape[1])
    sampled = sample_bezier_contour(contour, samples_per_segment=samples_per_segment)
    if len(sampled) < 3:
        return np.zeros((rows, cols), dtype=bool)
    pixels = [
        (float(point[0]) * max(cols - 1, 1), float(point[1]) * max(rows - 1, 1))
        for point in sampled
    ]
    image = Image.new("L", (cols, rows), 0)
    ImageDraw.Draw(image).polygon(pixels, fill=255)
    return np.asarray(image, dtype=np.uint8) > 0


def apply_bezier_contours(mask, contours):
    """Apply ordered replace/add/remove/intersect contours to a footprint."""
    result = np.asarray(mask, dtype=bool).copy()
    applied = []
    for raw in contours or ():
        contour = normalize_bezier_contour(raw)
        if contour is None or not contour["closed"]:
            continue
        region = rasterize_bezier_contour(contour, result.shape)
        if not region.any():
            continue
        before = result.copy()
        operation = contour["operation"]
        if operation == "replace":
            result = region
        elif operation == "add":
            result |= region
        elif operation == "remove":
            result &= ~region
        else:
            result &= region
        applied.append(
            {
                "operation": operation,
                "changed_pixel_count": int(np.count_nonzero(before != result)),
                "sampled_point_count": int(len(sample_bezier_contour(contour))),
            }
        )
    return result, {
        "requested_contour_count": len(tuple(contours or ())),
        "applied_contour_count": len(applied),
        "changed_pixel_count": int(sum(item["changed_pixel_count"] for item in applied)),
        "contours": applied,
    }


def _smooth_handles(anchors):
    result = []
    count = len(anchors)
    for index, anchor in enumerate(anchors):
        previous = np.asarray(anchors[(index - 1) % count], dtype=float)
        current = np.asarray(anchor, dtype=float)
        following = np.asarray(anchors[(index + 1) % count], dtype=float)
        tangent = (following - previous) / 6.0
        result.append(
            {
                "anchor": current.tolist(),
                "in": np.clip(current - tangent, 0.0, 1.0).tolist(),
                "out": np.clip(current + tangent, 0.0, 1.0).tolist(),
            }
        )
    return result


def default_bezier_contour_from_mask(mask, maximum_anchors=24):
    """Create an editable smooth contour from the largest mask boundary."""
    values = np.asarray(mask, dtype=bool)
    loops = trace_boundary_loops(boundary_edges_from_mask(values))
    closed = [simplify_collinear_points(loop) for loop in loops if len(loop) >= 4 and loop[0] == loop[-1]]
    if not closed:
        return None
    loop = max(closed, key=len)[:-1]
    maximum = max(4, int(maximum_anchors))
    stride = max(1, int(math.ceil(len(loop) / maximum)))
    selected = loop[::stride]
    if len(selected) < 4:
        selected = loop
    rows, cols = values.shape
    anchors = [
        [float(np.clip(x / max(cols, 1), 0.0, 1.0)), float(np.clip(y / max(rows, 1), 0.0, 1.0))]
        for x, y in selected
    ]
    return {
        "operation": "replace",
        "closed": True,
        "points": _smooth_handles(anchors),
    }


def map_contour_points(contour, mapper):
    """Map anchors and handles through a caller-provided normalized point mapper."""
    normalized = normalize_bezier_contour(contour)
    if normalized is None:
        return None
    mapped = dict(normalized)
    mapped["points"] = []
    for point in normalized["points"]:
        mapped["points"].append(
            {
                "anchor": list(mapper(*point["anchor"])),
                "in": list(mapper(*point["in"])),
                "out": list(mapper(*point["out"])),
            }
        )
    return normalize_bezier_contour(mapped)


def default_bezier_ellipse(operation="add", center=(0.5, 0.5), radii=(0.3, 0.3)):
    """Return a reusable four-anchor cubic approximation of an ellipse."""
    center_x, center_y = float(center[0]), float(center[1])
    radius_x, radius_y = abs(float(radii[0])), abs(float(radii[1]))
    handle_ratio = 0.5522847498307936
    horizontal_handle = radius_x * handle_ratio
    vertical_handle = radius_y * handle_ratio
    contour = {
        "operation": str(operation),
        "closed": True,
        "points": [
            {
                "anchor": [center_x, center_y - radius_y],
                "in": [center_x - horizontal_handle, center_y - radius_y],
                "out": [center_x + horizontal_handle, center_y - radius_y],
            },
            {
                "anchor": [center_x + radius_x, center_y],
                "in": [center_x + radius_x, center_y - vertical_handle],
                "out": [center_x + radius_x, center_y + vertical_handle],
            },
            {
                "anchor": [center_x, center_y + radius_y],
                "in": [center_x + horizontal_handle, center_y + radius_y],
                "out": [center_x - horizontal_handle, center_y + radius_y],
            },
            {
                "anchor": [center_x - radius_x, center_y],
                "in": [center_x - radius_x, center_y + vertical_handle],
                "out": [center_x - radius_x, center_y - vertical_handle],
            },
        ],
    }
    return normalize_bezier_contour(contour)
