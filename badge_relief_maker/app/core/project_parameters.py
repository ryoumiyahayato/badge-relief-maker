"""Boundary between persisted project settings and runtime relief parameters."""

from .marker_schema import HEIGHT_MARKER_TYPES, HEIGHT_VALUE_KEYS, POLYGON_SHAPES, SMOOTH_OPERATIONS
from .options import (
    ADAPTIVE_MESH_DEFAULT,
    EDGE_STYLES,
    FOOTPRINT_MODES,
    HEIGHT_MODES,
    LOCK_CONFIRMED_REGIONS_DEFAULT,
    MASK_MODES,
    PROCESS_PROFILES,
)
from .quality_modes import normalize_quality_mode, quality_preset
from .relief_parameters import ReliefParameters
from .validation import finite_number, integer


def project_side(project, side_name):
    """Return the image record and saved parameters for one project side."""
    if side_name == "front":
        return project.front_image, project.front_relief
    if side_name == "back":
        return project.back_image, project.back_relief
    raise ValueError(f"unsupported project side: {side_name}")


def _validate_side_parameters(side, label):
    finite_number(side.relief_height_mm, f"{label} relief_height_mm", nonnegative=True)
    finite_number(side.background_depth_mm, f"{label} background_depth_mm", nonnegative=True)
    finite_number(side.luminance_threshold, f"{label} luminance_threshold", nonnegative=True)
    finite_number(side.minimum_thickness_mm, f"{label} minimum_thickness_mm", nonnegative=True)
    finite_number(side.uniform_height_normalized, f"{label} uniform_height_normalized", nonnegative=True, maximum=1.0)
    finite_number(side.smooth_strength, f"{label} smooth_strength", nonnegative=True, maximum=1.0)
    finite_number(side.detail_sharpness, f"{label} detail_sharpness", nonnegative=True, maximum=1.0)
    integer(side.alpha_threshold, f"{label} alpha_threshold", minimum=0, maximum=255)
    integer(side.crop_padding_px, f"{label} crop_padding_px", minimum=0)
    if str(side.mask_mode).strip().lower() not in MASK_MODES:
        raise ValueError(f"unsupported {label} mask_mode: {side.mask_mode}")
    if str(side.height_mode).strip().lower() not in HEIGHT_MODES:
        raise ValueError(f"unsupported {label} height_mode: {side.height_mode}")
    if str(side.process_profile).strip().lower() not in PROCESS_PROFILES:
        raise ValueError(f"unsupported {label} process_profile: {side.process_profile}")


def _validate_double_alignment(project):
    alignment = project.double_side
    finite_number(alignment.back_scale, "back_scale", positive=True)
    finite_number(alignment.back_rotation_deg, "back_rotation_deg")
    finite_number(alignment.back_offset_x_mm, "back_offset_x_mm")
    finite_number(alignment.back_offset_y_mm, "back_offset_y_mm")
    if str(alignment.footprint_mode).strip().lower() not in FOOTPRINT_MODES:
        raise ValueError("footprint_mode must be union, intersection, front or back")


def validate_project_parameters(project, *, double_side=False, side_name=None, fused=False):
    """Validate only the saved settings consumed by the requested build."""
    dimensions = project.dimensions
    width = finite_number(dimensions.width_mm, "width_mm", positive=True)
    height = finite_number(dimensions.height_mm, "height_mm", positive=True)
    base = finite_number(dimensions.base_thickness_mm, "base_thickness_mm", nonnegative=True)
    total = None
    if double_side or fused or side_name is None:
        total = finite_number(dimensions.total_thickness_mm, "total_thickness_mm", positive=True)
    if double_side and not fused and total < base * 2.0:
        raise ValueError("total_thickness_mm must be at least twice base_thickness_mm for a double-side placeholder")

    if double_side or fused or side_name is None:
        sides = ((project.front_relief, "front"), (project.back_relief, "back"))
    else:
        _, selected_side = project_side(project, side_name)
        sides = ((selected_side, side_name),)
    for side, label in sides:
        _validate_side_parameters(side, label)

    edge = project.edge
    finite_number(edge.rim_width_mm, "rim_width_mm", nonnegative=True)
    finite_number(edge.rim_height_mm, "rim_height_mm", nonnegative=True)
    finite_number(edge.bevel_mm, "bevel_mm", nonnegative=True)
    finite_number(edge.radius_mm, "radius_mm", nonnegative=True)
    integer(edge.rim_width_px, "rim_width_px", minimum=0)
    integer(edge.contour_smoothing_iterations, "contour_smoothing_iterations", minimum=0)
    if str(edge.edge_style).strip().lower() not in EDGE_STYLES:
        raise ValueError(f"unsupported edge_style: {edge.edge_style}")
    if fused:
        front_profile = str(project.front_relief.process_profile).strip().lower()
        back_profile = str(project.back_relief.process_profile).strip().lower()
        if front_profile != back_profile:
            raise ValueError("front and back process_profile must match for a fused build")
        _validate_double_alignment(project)
    return width, height


def resolve_double_quality(project, quality_mode=None):
    """Return one quality mode for both sides, rejecting ambiguous saved state."""
    if quality_mode is not None:
        return normalize_quality_mode(quality_mode)
    front_quality = normalize_quality_mode(project.front_relief.quality_mode)
    back_quality = normalize_quality_mode(project.back_relief.quality_mode)
    if front_quality != back_quality:
        raise ValueError("front and back quality_mode must match unless a build quality override is provided")
    return front_quality


def _potential_height_marker(data):
    if not isinstance(data, dict) or not data:
        return False
    operation = str(data.get("operation", data.get("mode", "set"))).lower()
    if operation not in SMOOTH_OPERATIONS and not any(key in data for key in HEIGHT_VALUE_KEYS):
        return False
    shape = str(data.get("shape", data.get("shape_type", "circle"))).lower()
    if shape in POLYGON_SHAPES:
        points = data.get("points", data.get("vertices", data.get("polygon_points")))
        return isinstance(points, (list, tuple)) and len(points) >= 3
    return ("x" in data or "center_x" in data) and ("y" in data or "center_y" in data)


def _manual_height_markers(project, side_name):
    allowed_targets = {side_name, "both", "heightmap", "relief"}
    result = []
    for marker in getattr(project, "manual_markers", []):
        marker_type = str(getattr(marker, "marker_type", "")).lower()
        target = str(getattr(marker, "target", "")).lower()
        raw_data = getattr(marker, "data", {})
        if marker_type not in HEIGHT_MARKER_TYPES or target not in allowed_targets or not _potential_height_marker(raw_data):
            continue
        data = dict(raw_data)
        data["marker_type"] = marker_type
        data["target"] = target
        result.append(data)
    return tuple(result)


def _optional_tuple(value):
    return tuple(value) if isinstance(value, (list, tuple)) else None


def _perspective_tuple(value):
    if not isinstance(value, (list, tuple)):
        return None
    try:
        return tuple(tuple(point) for point in value)
    except TypeError:
        return None


def map_project_relief_parameters(project, side_name="front", quality_mode=None):
    """Map persisted project records into one immutable runtime parameter object."""
    _, side = project_side(project, side_name)
    preset = quality_preset(quality_mode or side.quality_mode)
    edge = project.edge
    rim_enabled = bool(getattr(edge, "rim_enabled", False))
    parameters = ReliefParameters(
        width_mm=project.dimensions.width_mm,
        height_mm=project.dimensions.height_mm,
        base_thickness_mm=project.dimensions.base_thickness_mm,
        relief_height_mm=side.relief_height_mm,
        invert_height=bool(side.invert_height),
        mask_mode=str(side.mask_mode),
        alpha_threshold=int(side.alpha_threshold),
        luminance_threshold=float(side.luminance_threshold),
        minimum_thickness_mm=float(side.minimum_thickness_mm),
        crop_to_foreground=bool(side.crop_to_foreground),
        crop_padding_px=int(side.crop_padding_px),
        max_grid_cells=preset["max_grid_cells"],
        min_component_pixels=preset["min_component_pixels"],
        fill_hole_pixels=preset["fill_hole_pixels"],
        mask_smooth_iterations=preset["mask_smooth_iterations"],
        contour_smoothing_iterations=int(getattr(edge, "contour_smoothing_iterations", 1)),
        rim_width_px=max(0, int(getattr(edge, "rim_width_px", 0))) if rim_enabled else 0,
        rim_width_mm=float(getattr(edge, "rim_width_mm", 0.0)) if rim_enabled else 0.0,
        rim_height_mm=float(edge.rim_height_mm) if rim_enabled else 0.0,
        rim_profile=str(getattr(edge, "rim_profile", "flat") or "flat"),
        edge_style=str(getattr(edge, "edge_style", "straight") or "straight"),
        bevel_mm=float(getattr(edge, "bevel_mm", 0.0)),
        radius_mm=float(getattr(edge, "radius_mm", 0.0)),
        height_mode=str(getattr(side, "height_mode", "grayscale") or "grayscale"),
        background_depth_mm=float(getattr(side, "background_depth_mm", 0.0)),
        uniform_height_normalized=float(getattr(side, "uniform_height_normalized", 1.0)),
        smooth_strength=float(getattr(side, "smooth_strength", 0.0)),
        detail_sharpness=float(getattr(side, "detail_sharpness", 0.0)),
        process_profile=str(getattr(side, "process_profile", "general") or "general"),
        manual_crop_box=_optional_tuple(getattr(side, "manual_crop_box", None)),
        perspective_quad=_perspective_tuple(getattr(side, "perspective_quad", None)),
        manual_mask_edits=tuple(getattr(side, "mask_edits", []) or []),
        region_layers=tuple(getattr(side, "region_layers", []) or []),
        manual_height_markers=_manual_height_markers(project, side_name),
        semantic_annotations=tuple(getattr(side, "semantic_annotations", []) or []),
        lock_confirmed_regions=bool(
            getattr(side, "lock_confirmed_regions", LOCK_CONFIRMED_REGIONS_DEFAULT)
        ),
        bezier_contours=tuple(getattr(side, "bezier_contours", []) or []),
        adaptive_mesh_enabled=bool(
            getattr(side, "adaptive_mesh_enabled", ADAPTIVE_MESH_DEFAULT)
        ),
        adaptive_coarse_cell_px=int(preset["adaptive_coarse_cell_px"]),
    )
    return parameters, preset["quality_mode"]


def relief_parameters_from_project(project, side_name="front", quality_mode=None):
    """Return validated runtime parameters for builds and GUI previews."""
    validate_project_parameters(project, side_name=side_name)
    return map_project_relief_parameters(project, side_name, quality_mode)
