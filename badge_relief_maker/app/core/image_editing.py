"""Deterministic perspective, crop and manual mask-edit helpers."""

import numpy as np
from PIL import Image, ImageDraw


def validate_crop_box(box, image_shape):
    if box is None:
        return None
    try:
        x0, y0, x1, y1 = (int(round(float(value))) for value in box)
    except (TypeError, ValueError) as exc:
        raise ValueError("manual_crop_box must contain x0, y0, x1 and y1") from exc
    rows, cols = image_shape[:2]
    x0 = min(max(x0, 0), cols)
    x1 = min(max(x1, 0), cols)
    y0 = min(max(y0, 0), rows)
    y1 = min(max(y1, 0), rows)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("manual_crop_box must select a non-empty image region")
    return x0, y0, x1, y1


def crop_rgba(rgba, box):
    rgba = np.asarray(rgba)
    normalized = validate_crop_box(box, rgba.shape)
    if normalized is None:
        return rgba.copy(), None
    x0, y0, x1, y1 = normalized
    return rgba[y0:y1, x0:x1].copy(), normalized


def _perspective_coefficients(source_points, output_size):
    width, height = output_size
    destination = [(0.0, 0.0), (width - 1.0, 0.0), (width - 1.0, height - 1.0), (0.0, height - 1.0)]
    matrix = []
    values = []
    for (x_out, y_out), (x_src, y_src) in zip(destination, source_points):
        matrix.append([x_out, y_out, 1.0, 0.0, 0.0, 0.0, -x_src * x_out, -x_src * y_out])
        values.append(x_src)
        matrix.append([0.0, 0.0, 0.0, x_out, y_out, 1.0, -y_src * x_out, -y_src * y_out])
        values.append(y_src)
    try:
        return np.linalg.solve(np.asarray(matrix, dtype=float), np.asarray(values, dtype=float)).tolist()
    except np.linalg.LinAlgError as exc:
        raise ValueError("perspective_quad is degenerate") from exc


def rectify_perspective(rgba, perspective_quad):
    """Rectify a normalized TL,TR,BR,BL source quadrilateral to a rectangle."""
    rgba = np.asarray(rgba, dtype=np.uint8)
    if perspective_quad is None:
        return rgba.copy(), None
    try:
        raw_points = list(perspective_quad)
        if len(raw_points) != 4:
            raise ValueError
        rows, cols = rgba.shape[:2]
        points = []
        for point in raw_points:
            x, y = float(point[0]), float(point[1])
            if not (np.isfinite(x) and np.isfinite(y) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError
            points.append((x * max(cols - 1, 1), y * max(rows - 1, 1)))
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError("perspective_quad must contain four normalized x/y points") from exc

    top = np.linalg.norm(np.subtract(points[1], points[0]))
    bottom = np.linalg.norm(np.subtract(points[2], points[3]))
    left = np.linalg.norm(np.subtract(points[3], points[0]))
    right = np.linalg.norm(np.subtract(points[2], points[1]))
    width = max(2, int(round(max(top, bottom))))
    height = max(2, int(round(max(left, right))))
    coefficients = _perspective_coefficients(points, (width, height))
    image = Image.fromarray(rgba, mode="RGBA")
    corrected = image.transform(
        (width, height),
        Image.Transform.PERSPECTIVE,
        coefficients,
        resample=Image.Resampling.BICUBIC,
    )
    return np.asarray(corrected), {"source_quad_normalized": [list(point) for point in raw_points], "output_size": [width, height]}


def _edit_region(shape, edit):
    rows, cols = shape
    coordinate_space = str(edit.get("coordinate_space", "normalized")).lower()
    normalized = coordinate_space not in {"pixel", "pixels", "image_pixel", "final"}
    edit_shape = str(edit.get("shape", "circle")).lower()
    if edit_shape in {"polygon", "poly", "freeform"}:
        points = edit.get("points", [])
        converted = []
        for point in points:
            x, y = (point.get("x"), point.get("y")) if isinstance(point, dict) else point[:2]
            x, y = float(x), float(y)
            if normalized:
                x *= max(cols - 1, 1)
                y *= max(rows - 1, 1)
            converted.append((x, y))
        if len(converted) < 3:
            return np.zeros(shape, dtype=bool)
        image = Image.new("L", (cols, rows), 0)
        ImageDraw.Draw(image).polygon(converted, fill=255)
        return np.asarray(image) > 0

    x = float(edit.get("x", edit.get("center_x", 0.5)))
    y = float(edit.get("y", edit.get("center_y", 0.5)))
    if normalized:
        x *= max(cols - 1, 1)
        y *= max(rows - 1, 1)
    yy, xx = np.ogrid[:rows, :cols]
    if edit_shape in {"rectangle", "rect", "box"}:
        width = float(edit.get("width_normalized", edit.get("width_px", 0.05)))
        height = float(edit.get("height_size_normalized", edit.get("height_px", 0.05)))
        if normalized and "width_px" not in edit:
            width *= cols
        if normalized and "height_px" not in edit:
            height *= rows
        return (np.abs(xx - x) <= width / 2.0) & (np.abs(yy - y) <= height / 2.0)

    radius = float(edit.get("radius_normalized", edit.get("radius_px", 0.02)))
    if normalized and "radius_px" not in edit:
        radius *= min(rows, cols)
    return (xx - x) ** 2 + (yy - y) ** 2 <= radius**2


def apply_mask_edits(mask, edits=()):
    """Apply normalized or pixel add/remove/toggle mask edits."""
    result = np.asarray(mask, dtype=bool).copy()
    report = {"requested_edit_count": 0, "applied_edit_count": 0, "changed_pixel_count": 0}
    changed = np.zeros(result.shape, dtype=bool)
    for edit in edits or ():
        report["requested_edit_count"] += 1
        if not isinstance(edit, dict):
            continue
        try:
            region = _edit_region(result.shape, edit)
        except (TypeError, ValueError, IndexError):
            continue
        before = result.copy()
        operation = str(edit.get("operation", "add")).lower()
        if operation in {"remove", "subtract", "erase"}:
            result[region] = False
        elif operation == "toggle":
            result[region] = ~result[region]
        else:
            result[region] = True
        delta = before != result
        if delta.any():
            report["applied_edit_count"] += 1
            changed |= delta
    report["changed_pixel_count"] = int(changed.sum())
    return result, report
