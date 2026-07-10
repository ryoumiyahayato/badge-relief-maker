"""Transform saved manual marker coordinates through crop and resize steps."""

from .height_markers import normalize_manual_height_marker


def _scale_point(value, source_size, crop_offset, crop_size, target_size, normalized):
    coordinate = float(value) * max(source_size - 1, 1) if normalized else float(value)
    coordinate -= float(crop_offset)
    if crop_size <= 1 or target_size <= 1:
        return 0.0
    return coordinate * float(target_size - 1) / float(crop_size - 1)


def _dimension_scale(crop_size, target_size):
    if crop_size <= 0:
        return 1.0
    return float(target_size) / float(crop_size)


def _transform_points(points, normalized, original_shape, crop_box, cropped_shape, resized_shape):
    original_rows, original_cols = original_shape
    crop_x0, crop_y0 = (crop_box[0], crop_box[1]) if crop_box is not None else (0, 0)
    crop_rows, crop_cols = cropped_shape
    resized_rows, resized_cols = resized_shape
    result = []
    for point in points:
        if isinstance(point, dict):
            x_value = point.get("x")
            y_value = point.get("y")
        else:
            x_value, y_value = point[0], point[1]
        x = _scale_point(x_value, original_cols, crop_x0, crop_cols, resized_cols, normalized)
        y = _scale_point(y_value, original_rows, crop_y0, crop_rows, resized_rows, normalized)
        result.append((x, y))
    return result


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


def _transform_marker(marker, original_shape, crop_box, cropped_shape, resized_shape):
    if not isinstance(marker, dict):
        return None

    original_rows, original_cols = (int(original_shape[0]), int(original_shape[1]))
    crop_rows, crop_cols = (int(cropped_shape[0]), int(cropped_shape[1]))
    resized_rows, resized_cols = (int(resized_shape[0]), int(resized_shape[1]))
    crop_x0, crop_y0 = (int(crop_box[0]), int(crop_box[1])) if crop_box is not None else (0, 0)
    x_dimension_scale = _dimension_scale(crop_cols, resized_cols)
    y_dimension_scale = _dimension_scale(crop_rows, resized_rows)
    radius_scale = (x_dimension_scale + y_dimension_scale) * 0.5

    data = dict(marker)
    coordinate_space = str(data.get("coordinate_space", data.get("space", "normalized"))).lower()
    shape = str(data.get("shape", data.get("shape_type", data.get("region_shape", "circle")))).lower()

    if coordinate_space in {"processed", "heightmap", "final"}:
        data["coordinate_space"] = "pixel"
        return data if normalize_manual_height_marker(data, resized_shape) is not None else None

    normalized = coordinate_space not in {"pixel", "pixels", "image_pixel"}
    if shape in {"polygon", "poly", "freeform", "free_form"}:
        points_key = next((key for key in ["points", "vertices", "polygon_points"] if key in data), None)
        if points_key is None:
            return None
        data["points"] = _transform_points(
            list(data[points_key]), normalized, original_shape, crop_box, cropped_shape, resized_shape
        )
        for key in ["vertices", "polygon_points"]:
            data.pop(key, None)
    else:
        x_key = "x" if "x" in data else "center_x" if "center_x" in data else None
        y_key = "y" if "y" in data else "center_y" if "center_y" in data else None
        if x_key is None or y_key is None:
            return None
        data["x"] = _scale_point(data[x_key], original_cols, crop_x0, crop_cols, resized_cols, normalized)
        data["y"] = _scale_point(data[y_key], original_rows, crop_y0, crop_rows, resized_rows, normalized)
        data.pop("center_x", None)
        data.pop("center_y", None)

    if "radius_px" in data:
        data["radius_px"] = float(data["radius_px"]) * radius_scale
    elif "radius" in data:
        data["radius_px"] = float(data.pop("radius")) * radius_scale
    elif "radius_normalized" in data:
        original_radius = float(data.pop("radius_normalized")) * min(original_rows, original_cols)
        data["radius_px"] = original_radius * radius_scale

    for key in ["width_px", "rect_width_px", "region_width_px", "box_width_px"]:
        if key in data:
            data[key] = float(data[key]) * x_dimension_scale
    for key in ["height_px", "rect_height_px", "region_height_px", "box_height_px"]:
        if key in data:
            data[key] = float(data[key]) * y_dimension_scale
    if "size_px" in data:
        data["size_px"] = float(data["size_px"]) * radius_scale

    for key in ["width_normalized", "rect_width_normalized", "region_width_normalized", "box_width_normalized"]:
        if key in data:
            data["width_px"] = float(data.pop(key)) * max(original_cols - 1, 1) * x_dimension_scale
            break
    for key in ["rect_height_normalized", "region_height_normalized", "box_height_normalized", "height_size_normalized"]:
        if key in data:
            data["height_px"] = float(data.pop(key)) * max(original_rows - 1, 1) * y_dimension_scale
            break

    data["coordinate_space"] = "pixel"
    return data if normalize_manual_height_marker(data, resized_shape) is not None else None


def transform_manual_height_markers(markers, original_shape, crop_box, cropped_shape, resized_shape):
    """Map valid marker geometry from original-image coordinates to the resized grid.

    Normalized marker coordinates are interpreted against the original image.
    Pixel coordinates are also interpreted in original-image pixels. Callers may
    opt out for already processed pixel data with coordinate_space set to
    ``processed``, ``heightmap`` or ``final``. Malformed markers are ignored rather
    than aborting the complete build.
    """
    transformed = []
    for marker in _marker_list(markers):
        try:
            data = _transform_marker(marker, original_shape, crop_box, cropped_shape, resized_shape)
        except (TypeError, ValueError, IndexError, KeyError, OverflowError):
            data = None
        if data is not None:
            transformed.append(data)
    return tuple(transformed)
