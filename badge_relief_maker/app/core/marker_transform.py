"""Transform saved manual marker coordinates through image-processing stages."""

from .height_markers import normalize_manual_height_marker
from .image_transform import ImageTransform


_POLYGON_SHAPES = {"polygon", "poly", "freeform", "free_form"}
_NORMALIZED_GRID_SPACES = {
    "final_normalized",
    "geometry_normalized",
    "target_normalized",
    "processed_normalized",
    "heightmap_normalized",
    "resized_normalized",
}


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


def _point_values(point):
    if isinstance(point, dict):
        return point.get("x"), point.get("y")
    return point[0], point[1]


def _transform_original_points(points, normalized, transform):
    result = []
    for point in points:
        x_value, y_value = _point_values(point)
        result.append(transform.original_to_target_point(x_value, y_value, normalized=normalized))
    return result


def _transform_grid_points(points, coordinate_space, transform):
    result = []
    normalized = coordinate_space in _NORMALIZED_GRID_SPACES
    for point in points:
        x_value, y_value = _point_values(point)
        if normalized:
            mapped = transform.normalized_grid_to_target_point(x_value, y_value, coordinate_space)
        else:
            mapped = transform.input_grid_to_target_point(x_value, y_value, coordinate_space)
        result.append(mapped)
    return result


def _transform_grid_dimensions(data, coordinate_space, transform):
    """Normalize grid-space marker dimensions to target-grid pixels."""
    space = str(coordinate_space).lower()
    if space in {"final_normalized", "geometry_normalized", "target_normalized"}:
        target_rows, target_cols = transform.target_shape
        if "radius_normalized" in data:
            data["radius_px"] = float(data.pop("radius_normalized")) * min(target_rows, target_cols)
        for key in ["width_normalized", "rect_width_normalized", "region_width_normalized", "box_width_normalized"]:
            if key in data:
                data["width_px"] = float(data.pop(key)) * max(target_cols - 1, 1)
                break
        for key in ["rect_height_normalized", "region_height_normalized", "box_height_normalized", "height_size_normalized"]:
            if key in data:
                data["height_px"] = float(data.pop(key)) * max(target_rows - 1, 1)
                break
        return data

    if space in {"processed_normalized", "heightmap_normalized", "resized_normalized"}:
        resized_rows, resized_cols = transform.resized_shape
        if "radius_normalized" in data:
            data["radius_px"] = float(data.pop("radius_normalized")) * min(resized_rows, resized_cols)
        for key in ["width_normalized", "rect_width_normalized", "region_width_normalized", "box_width_normalized"]:
            if key in data:
                data["width_px"] = float(data.pop(key)) * max(resized_cols - 1, 1)
                break
        for key in ["rect_height_normalized", "region_height_normalized", "box_height_normalized", "height_size_normalized"]:
            if key in data:
                data["height_px"] = float(data.pop(key)) * max(resized_rows - 1, 1)
                break
    return data


def _map_grid_marker_to_target(data, shape, coordinate_space, transform):
    if shape in _POLYGON_SHAPES:
        points_key = next((key for key in ["points", "vertices", "polygon_points"] if key in data), None)
        if points_key is None:
            return None
        data["points"] = _transform_grid_points(list(data[points_key]), coordinate_space, transform)
        for key in ["vertices", "polygon_points"]:
            data.pop(key, None)
    else:
        x_key = "x" if "x" in data else "center_x" if "center_x" in data else None
        y_key = "y" if "y" in data else "center_y" if "center_y" in data else None
        if x_key is None or y_key is None:
            return None
        if coordinate_space in _NORMALIZED_GRID_SPACES:
            data["x"], data["y"] = transform.normalized_grid_to_target_point(data[x_key], data[y_key], coordinate_space)
        else:
            data["x"], data["y"] = transform.input_grid_to_target_point(data[x_key], data[y_key], coordinate_space)
        data.pop("center_x", None)
        data.pop("center_y", None)
    _transform_grid_dimensions(data, coordinate_space, transform)
    data["coordinate_space"] = "pixel"
    return data


def _transform_marker(marker, transform):
    if not isinstance(marker, dict):
        return None

    data = dict(marker)
    coordinate_space = str(data.get("coordinate_space", data.get("space", "normalized"))).lower()
    shape = str(data.get("shape", data.get("shape_type", data.get("region_shape", "circle")))).lower()

    if coordinate_space in {"processed", "heightmap", "final", *_NORMALIZED_GRID_SPACES}:
        data = _map_grid_marker_to_target(data, shape, coordinate_space, transform)
        return data if data is not None and normalize_manual_height_marker(data, transform.target_shape) is not None else None

    normalized = coordinate_space not in {"pixel", "pixels", "image_pixel"}
    if shape in _POLYGON_SHAPES:
        points_key = next((key for key in ["points", "vertices", "polygon_points"] if key in data), None)
        if points_key is None:
            return None
        data["points"] = _transform_original_points(list(data[points_key]), normalized, transform)
        for key in ["vertices", "polygon_points"]:
            data.pop(key, None)
    else:
        x_key = "x" if "x" in data else "center_x" if "center_x" in data else None
        y_key = "y" if "y" in data else "center_y" if "center_y" in data else None
        if x_key is None or y_key is None:
            return None
        data["x"], data["y"] = transform.original_to_target_point(data[x_key], data[y_key], normalized=normalized)
        data.pop("center_x", None)
        data.pop("center_y", None)

    if "radius_px" in data:
        data["radius_px"] = transform.original_radius_to_processed(data["radius_px"], normalized=False)
    elif "radius" in data:
        data["radius_px"] = transform.original_radius_to_processed(data.pop("radius"), normalized=False)
    elif "radius_normalized" in data:
        data["radius_px"] = transform.original_radius_to_processed(data.pop("radius_normalized"), normalized=True)

    for key in ["width_px", "rect_width_px", "region_width_px", "box_width_px"]:
        if key in data:
            data[key] = transform.original_length_to_processed(data[key], "x", normalized=False)
    for key in ["height_px", "rect_height_px", "region_height_px", "box_height_px"]:
        if key in data:
            data[key] = transform.original_length_to_processed(data[key], "y", normalized=False)
    if "size_px" in data:
        data["size_px"] = transform.original_radius_to_processed(data["size_px"], normalized=False)

    for key in ["width_normalized", "rect_width_normalized", "region_width_normalized", "box_width_normalized"]:
        if key in data:
            data["width_px"] = transform.original_length_to_processed(data.pop(key), "x", normalized=True)
            break
    for key in ["rect_height_normalized", "region_height_normalized", "box_height_normalized", "height_size_normalized"]:
        if key in data:
            data["height_px"] = transform.original_length_to_processed(data.pop(key), "y", normalized=True)
            break

    data["coordinate_space"] = "pixel"
    return data if normalize_manual_height_marker(data, transform.target_shape) is not None else None


def transform_manual_height_markers(
    markers,
    original_shape=None,
    crop_box=None,
    cropped_shape=None,
    resized_shape=None,
    image_transform=None,
):
    """Map valid marker geometry into the actual marker-application grid.

    With a geometry crop, original and processed coordinates are shifted into the
    final tight grid. ``coordinate_space='final'`` is already expressed in final
    pixels. ``final_normalized`` and aliases are normalized to that same grid.
    Existing callers may still provide individual processing values.
    """
    transform = image_transform
    if transform is None:
        transform = ImageTransform(
            original_shape=original_shape,
            crop_box=crop_box,
            cropped_shape=cropped_shape,
            resized_shape=resized_shape,
        )
    if not isinstance(transform, ImageTransform):
        raise TypeError("image_transform must be an ImageTransform")

    transformed = []
    for marker in _marker_list(markers):
        try:
            data = _transform_marker(marker, transform)
        except (TypeError, ValueError, IndexError, KeyError, OverflowError):
            data = None
        if data is not None:
            transformed.append(data)
    return tuple(transformed)
