"""Shared vocabulary and input normalization for manual relief markers."""

HEIGHT_MARKER_TYPES = frozenset({"height", "height_override", "set_height"})
HEIGHT_TARGETS = frozenset({"heightmap", "relief", "front", "back", "both"})
SET_OPERATIONS = frozenset({"set", "replace", "override", "height_override", "set_height"})
ADD_OPERATIONS = frozenset({"add", "raise", "increase"})
SUBTRACT_OPERATIONS = frozenset({"subtract", "sub", "lower", "decrease"})
SMOOTH_OPERATIONS = frozenset({"smooth", "soften", "blur"})
POLYGON_SHAPES = frozenset({"polygon", "poly", "freeform", "free_form"})
RECTANGLE_SHAPES = frozenset({"rectangle", "rect", "box"})
POLYGON_POINT_KEYS = ("points", "vertices", "polygon_points")
WIDTH_PIXEL_KEYS = ("width_px", "rect_width_px", "region_width_px", "box_width_px")
HEIGHT_PIXEL_KEYS = ("height_px", "rect_height_px", "region_height_px", "box_height_px")
WIDTH_NORMALIZED_KEYS = ("width_normalized", "rect_width_normalized", "region_width_normalized", "box_width_normalized")
HEIGHT_NORMALIZED_KEYS = ("rect_height_normalized", "region_height_normalized", "box_height_normalized", "height_size_normalized")
PIXEL_COORDINATE_SPACES = frozenset({"pixel", "pixels", "image_pixel"})
HEIGHT_VALUE_KEYS = frozenset(
    {
        "height_normalized",
        "normalized_height",
        "value",
        "height",
        "delta",
        "delta_height",
        "height_delta",
        "strength",
    }
)


def marker_list(markers):
    """Normalize one marker or an iterable of markers into a list."""
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


def first_present_key(mapping, keys):
    """Return the first accepted alias present in a mapping."""
    return next((key for key in keys if key in mapping), None)
