"""Unified coordinate transforms for image, processing-grid and geometry stages."""

from dataclasses import dataclass, replace


def _shape(value, name):
    try:
        rows, cols = int(value[0]), int(value[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"{name} must contain rows and columns") from exc
    if rows <= 0 or cols <= 0:
        raise ValueError(f"{name} must be positive")
    return rows, cols


def _box(value, name):
    if value is None:
        return None
    try:
        x0, y0, x1, y1 = (int(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an x0, y0, x1, y1 box") from exc
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"{name} must have positive width and height")
    return x0, y0, x1, y1


@dataclass(frozen=True)
class ImageTransform:
    """Record the deterministic coordinate chain used by one image build.

    Coordinates use x/y ordering while array shapes use rows/columns. The first
    crop box is expressed in original-image coordinates. The optional geometry
    crop box is expressed in resized processing-grid coordinates.
    """

    original_shape: tuple[int, int]
    crop_box: tuple[int, int, int, int] | None
    cropped_shape: tuple[int, int]
    resized_shape: tuple[int, int]
    geometry_crop_box: tuple[int, int, int, int] | None = None
    geometry_shape: tuple[int, int] | None = None

    def __post_init__(self):
        object.__setattr__(self, "original_shape", _shape(self.original_shape, "original_shape"))
        object.__setattr__(self, "cropped_shape", _shape(self.cropped_shape, "cropped_shape"))
        object.__setattr__(self, "resized_shape", _shape(self.resized_shape, "resized_shape"))
        object.__setattr__(self, "crop_box", _box(self.crop_box, "crop_box"))
        object.__setattr__(self, "geometry_crop_box", _box(self.geometry_crop_box, "geometry_crop_box"))
        if self.geometry_shape is not None:
            object.__setattr__(self, "geometry_shape", _shape(self.geometry_shape, "geometry_shape"))
        if self.geometry_crop_box is not None and self.geometry_shape is None:
            raise ValueError("geometry_shape is required when geometry_crop_box is provided")

    @property
    def crop_offset(self):
        return (self.crop_box[0], self.crop_box[1]) if self.crop_box is not None else (0, 0)

    @property
    def target_shape(self):
        return self.geometry_shape or self.resized_shape

    @property
    def point_scale(self):
        crop_rows, crop_cols = self.cropped_shape
        resized_rows, resized_cols = self.resized_shape
        x_scale = 0.0 if crop_cols <= 1 or resized_cols <= 1 else float(resized_cols - 1) / float(crop_cols - 1)
        y_scale = 0.0 if crop_rows <= 1 or resized_rows <= 1 else float(resized_rows - 1) / float(crop_rows - 1)
        return x_scale, y_scale

    @property
    def dimension_scale(self):
        crop_rows, crop_cols = self.cropped_shape
        resized_rows, resized_cols = self.resized_shape
        return float(resized_cols) / float(crop_cols), float(resized_rows) / float(crop_rows)

    def original_to_processed_point(self, x, y, normalized=False):
        original_rows, original_cols = self.original_shape
        crop_x0, crop_y0 = self.crop_offset
        x_value = float(x) * max(original_cols - 1, 1) if normalized else float(x)
        y_value = float(y) * max(original_rows - 1, 1) if normalized else float(y)
        x_scale, y_scale = self.point_scale
        return (x_value - crop_x0) * x_scale, (y_value - crop_y0) * y_scale

    def original_to_target_point(self, x, y, normalized=False):
        """Map an original-image point into the grid where markers are applied."""
        processed = self.original_to_processed_point(x, y, normalized=normalized)
        return self.processed_to_geometry_point(*processed)

    def original_length_to_processed(self, value, axis, normalized=False):
        original_rows, original_cols = self.original_shape
        x_scale, y_scale = self.dimension_scale
        if axis == "x":
            source_extent = max(original_cols - 1, 1)
            return float(value) * source_extent * x_scale if normalized else float(value) * x_scale
        if axis == "y":
            source_extent = max(original_rows - 1, 1)
            return float(value) * source_extent * y_scale if normalized else float(value) * y_scale
        raise ValueError("axis must be 'x' or 'y'")

    def original_radius_to_processed(self, value, normalized=False):
        original_rows, original_cols = self.original_shape
        x_scale, y_scale = self.dimension_scale
        source_value = float(value) * min(original_rows, original_cols) if normalized else float(value)
        return source_value * ((x_scale + y_scale) * 0.5)

    def with_geometry_crop(self, geometry_crop_box, geometry_shape):
        """Return a transform extended with the final tight geometry crop."""
        return replace(self, geometry_crop_box=geometry_crop_box, geometry_shape=geometry_shape)

    def processed_to_geometry_point(self, x, y):
        if self.geometry_crop_box is None:
            return float(x), float(y)
        return float(x) - self.geometry_crop_box[0], float(y) - self.geometry_crop_box[1]

    def input_grid_to_target_point(self, x, y, coordinate_space):
        """Map processed or final-grid input coordinates to the marker target grid."""
        space = str(coordinate_space).lower()
        if space == "final":
            return float(x), float(y)
        return self.processed_to_geometry_point(x, y)

    def geometry_cell_size_mm(self, width_mm, height_mm):
        rows, cols = self.target_shape
        return float(width_mm) / float(cols), float(height_mm) / float(rows)

    def to_report(self):
        x_point_scale, y_point_scale = self.point_scale
        x_dimension_scale, y_dimension_scale = self.dimension_scale
        return {
            "coordinate_chain": "original_image -> crop -> resized_grid -> geometry_crop -> millimeters",
            "original_shape": list(self.original_shape),
            "crop_box": list(self.crop_box) if self.crop_box is not None else None,
            "cropped_shape": list(self.cropped_shape),
            "resized_shape": list(self.resized_shape),
            "geometry_crop_box": list(self.geometry_crop_box) if self.geometry_crop_box is not None else None,
            "geometry_shape": list(self.geometry_shape) if self.geometry_shape is not None else None,
            "target_shape": list(self.target_shape),
            "point_scale_xy": [x_point_scale, y_point_scale],
            "dimension_scale_xy": [x_dimension_scale, y_dimension_scale],
        }
