"""Parameter objects for relief building."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReliefParameters:
    """User controlled dimensions for a single side relief build."""

    width_mm: float = 80.0
    height_mm: float = 80.0
    base_thickness_mm: float = 2.0
    relief_height_mm: float = 3.0
    invert_height: bool = False
    alpha_threshold: int = 1
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
    rim_height_mm: float = 0.0
    rim_profile: str = "flat"


@dataclass(frozen=True)
class ReliefBuildResult:
    """Return value for a build step."""

    vertices: object
    faces: object
    report: dict
    output_path: str | None = None
