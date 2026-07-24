"""Parameter objects for relief building."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReliefParameters:
    """User controlled dimensions for a single side relief build."""

    width_mm: float = 80.0
    height_mm: float = 80.0
    base_thickness_mm: float = 2.0
    relief_height_mm: float = 3.0
    invert_height: bool = False
    mask_mode: str = "auto"
    alpha_threshold: int = 1
    luminance_threshold: float = 20.0
    minimum_thickness_mm: float = 0.8
    use_mask_footprint: bool = True
    crop_to_foreground: bool = True
    crop_padding_px: int = 1
    max_grid_cells: int = 20000
    min_component_pixels: int = 1
    fill_hole_pixels: int = 0
    mask_smooth_iterations: int = 0
    use_smoothed_side_walls: bool = False
    contour_smoothing_iterations: int = 1
    rim_width_px: int = 0
    rim_width_mm: float = 0.0
    rim_height_mm: float = 0.0
    rim_profile: str = "flat"
    edge_style: str = "straight"
    bevel_mm: float = 0.0
    radius_mm: float = 0.0
    height_mode: str = "grayscale"
    background_depth_mm: float = 0.0
    uniform_height_normalized: float = 1.0
    smooth_strength: float = 0.0
    detail_sharpness: float = 0.0
    process_profile: str = "general"
    manual_crop_box: tuple | None = None
    perspective_quad: tuple | None = None
    manual_mask_edits: tuple = field(default_factory=tuple)
    region_layers: tuple = field(default_factory=tuple)
    lineart_region_overrides: tuple = field(default_factory=tuple)
    manual_height_markers: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class ReliefBuildResult:
    """Return value for a build step."""

    vertices: object
    faces: object
    report: dict
    output_path: str | None = None


@dataclass(frozen=True)
class PreparedReliefField:
    """Processed mask and height field shared by preview and mesh workflows."""

    mask: object
    heightmap: object
    rgba: object
    image_transform: object
    report: dict
