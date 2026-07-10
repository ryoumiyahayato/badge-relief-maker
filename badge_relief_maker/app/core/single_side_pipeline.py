"""Runnable single-side relief pipeline for the local MVP."""

from pathlib import Path

import numpy as np

from .height_markers import apply_manual_height_markers
from .heightmap_generator import grayscale_heightmap
from .image_preprocess import load_image, normalize_alpha_background
from .image_transform import ImageTransform
from .manufacturability_check import basic_report
from .marker_transform import transform_manual_height_markers
from .mask_generator import foreground_mask
from .mask_processing import clean_mask, crop_to_mask, resize_mask_and_heightmap
from .masked_solid_builder import build_masked_relief_solid
from .mesh_exporter import export_mesh
from .mesh_repair import repair_mesh_basic
from .outline_extractor import outline_report
from .preview_exporter import save_heightmap_preview, save_mask_preview
from .relief_parameters import ReliefBuildResult, ReliefParameters
from .rim_builder import apply_outer_rim_to_heightmap
from .solid_builder import build_rectangular_relief_solid


_SUPPORTED_MASK_MODES = {"auto", "alpha", "luminance", "luminance-dark", "luminance-light"}
_SUPPORTED_RIM_PROFILES = {"flat", "linear", "smooth"}


def _side_wall_mode(params):
    if not params.use_mask_footprint:
        return "rectangle"
    return "grid_contour_closed"


def _finite_number(value, name, *, positive=False, nonnegative=False):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _integer(value, name, *, minimum=None, maximum=None):
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not np.isfinite(converted) or converted != round(converted):
        raise ValueError(f"{name} must be an integer")
    result = int(converted)
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return result


def _validate_parameters(params):
    _finite_number(params.width_mm, "width_mm", positive=True)
    _finite_number(params.height_mm, "height_mm", positive=True)
    _finite_number(params.base_thickness_mm, "base_thickness_mm", nonnegative=True)
    relief_height = _finite_number(params.relief_height_mm, "relief_height_mm", nonnegative=True)
    _finite_number(params.minimum_thickness_mm, "minimum_thickness_mm", nonnegative=True)
    _finite_number(params.luminance_threshold, "luminance_threshold", nonnegative=True)
    _finite_number(params.rim_width_mm, "rim_width_mm", nonnegative=True)
    rim_height = _finite_number(params.rim_height_mm, "rim_height_mm", nonnegative=True)
    _integer(params.alpha_threshold, "alpha_threshold", minimum=0, maximum=255)
    _integer(params.crop_padding_px, "crop_padding_px", minimum=0)
    _integer(params.max_grid_cells, "max_grid_cells", minimum=1)
    _integer(params.min_component_pixels, "min_component_pixels", minimum=0)
    _integer(params.fill_hole_pixels, "fill_hole_pixels", minimum=0)
    _integer(params.mask_smooth_iterations, "mask_smooth_iterations", minimum=0)
    _integer(params.contour_smoothing_iterations, "contour_smoothing_iterations", minimum=0)
    _integer(params.rim_width_px, "rim_width_px", minimum=0)
    if str(params.mask_mode).strip().lower() not in _SUPPORTED_MASK_MODES:
        raise ValueError(f"unsupported mask mode: {params.mask_mode}")
    if str(params.rim_profile).strip().lower() not in _SUPPORTED_RIM_PROFILES:
        raise ValueError("rim_profile must be 'flat', 'linear' or 'smooth'")
    if rim_height > 0.0 and relief_height <= 0.0:
        raise ValueError("relief_height_mm must be positive when rim_height_mm is requested")


def _effective_rim_width_px(params, mask):
    explicit = int(params.rim_width_px)
    if explicit > 0:
        return explicit
    requested_mm = float(getattr(params, "rim_width_mm", 0.0))
    if requested_mm <= 0.0 or not mask.any():
        return 0
    rows, cols = mask.shape
    cell_w_mm = float(params.width_mm) / float(max(cols, 1))
    cell_h_mm = float(params.height_mm) / float(max(rows, 1))
    average_cell_mm = max((cell_w_mm + cell_h_mm) * 0.5, 1e-12)
    return max(1, int(round(requested_mm / average_cell_mm)))


def _save_empty_previews(mask, preview_dir):
    if preview_dir is None:
        return
    preview_base = Path(preview_dir)
    preview_base.mkdir(parents=True, exist_ok=True)
    save_mask_preview(mask, preview_base / "mask_preview.png")
    save_heightmap_preview(np.zeros(mask.shape, dtype=np.float32), preview_base / "heightmap_preview.png")


def _blocking_topology_errors(report):
    topology = report["topology"]
    geometry = report["face_geometry"]
    components = report["components"]
    reasons = []
    if topology["boundary_edge_count"] > 0:
        reasons.append("open boundary edges")
    if topology["non_manifold_edge_count"] > 0:
        reasons.append("non-manifold edges")
    if topology["inconsistent_winding_edge_count"] > 0:
        reasons.append("inconsistent face winding")
    if geometry["invalid_face_count"] > 0:
        reasons.append("invalid face references")
    if geometry["zero_area_face_count"] > 0:
        reasons.append("zero-area faces")
    if components["inward_closed_component_count"] > 0:
        reasons.append("inward closed components")
    return reasons


def build_single_side_relief(image_path, output_path=None, parameters=None, preview_dir=None):
    """Build a closed rough relief solid from one local image."""
    params = parameters or ReliefParameters()
    _validate_parameters(params)

    loaded_image = load_image(image_path)
    rgba = normalize_alpha_background(loaded_image.rgba)
    mask, resolved_mask_mode = foreground_mask(
        rgba,
        mode=params.mask_mode,
        alpha_threshold=params.alpha_threshold,
        luminance_threshold=params.luminance_threshold,
    )

    original_shape = tuple(mask.shape)
    original_mask_pixel_count = int(mask.sum())
    mask, cleanup_report = clean_mask(
        mask,
        min_component_pixels=params.min_component_pixels,
        fill_hole_pixels=params.fill_hole_pixels,
        smooth_iterations=params.mask_smooth_iterations,
    )
    if not mask.any():
        _save_empty_previews(mask, preview_dir)
        raise ValueError("foreground mask is empty; adjust the mask mode, threshold, cleanup settings or source image")

    heightmap = grayscale_heightmap(rgba, mask=mask, invert=params.invert_height)
    crop_box = None
    if params.crop_to_foreground:
        mask, heightmap, crop_box = crop_to_mask(mask, heightmap, padding=params.crop_padding_px)

    shape_after_crop = tuple(mask.shape)
    mask, heightmap, resize_scale = resize_mask_and_heightmap(mask, heightmap, params.max_grid_cells)
    shape_after_resize = tuple(mask.shape)
    image_transform = ImageTransform(
        original_shape=original_shape,
        crop_box=crop_box,
        cropped_shape=shape_after_crop,
        resized_shape=shape_after_resize,
    )
    transformed_markers = transform_manual_height_markers(
        params.manual_height_markers,
        image_transform=image_transform,
    )
    heightmap, manual_height_report = apply_manual_height_markers(heightmap, mask, transformed_markers)
    manual_height_report["coordinate_transform"] = "ImageTransform.original_image_to_processed_grid"

    geometry_crop_box = None
    if params.crop_to_foreground:
        mask, heightmap, geometry_crop_box = crop_to_mask(mask, heightmap, padding=0)
    shape_for_geometry = tuple(mask.shape)
    image_transform = image_transform.with_geometry_crop(geometry_crop_box, shape_for_geometry)

    effective_rim_width_px = _effective_rim_width_px(params, mask)
    heightmap, rim_report = apply_outer_rim_to_heightmap(
        heightmap,
        mask,
        width_px=effective_rim_width_px,
        rim_height_mm=params.rim_height_mm,
        relief_height_mm=params.relief_height_mm,
        profile=params.rim_profile,
    )
    rim_report["requested_rim_width_mm"] = float(getattr(params, "rim_width_mm", 0.0))
    rim_report["effective_rim_width_px"] = int(effective_rim_width_px)
    cell_w_mm, cell_h_mm = image_transform.geometry_cell_size_mm(params.width_mm, params.height_mm)
    rim_report["geometry_cell_size_mm_xy"] = [cell_w_mm, cell_h_mm]

    outline = outline_report(
        mask,
        params.width_mm,
        params.height_mm,
        smoothing_iterations=params.contour_smoothing_iterations,
    )

    preview_paths = {}
    if preview_dir is not None:
        preview_base = Path(preview_dir)
        preview_base.mkdir(parents=True, exist_ok=True)
        preview_paths["mask_preview"] = save_mask_preview(mask, preview_base / "mask_preview.png")
        preview_paths["heightmap_preview"] = save_heightmap_preview(heightmap, preview_base / "heightmap_preview.png")

    if params.use_mask_footprint:
        vertices, faces = build_masked_relief_solid(
            heightmap,
            mask,
            params.width_mm,
            params.height_mm,
            params.base_thickness_mm,
            params.relief_height_mm,
            use_smoothed_side_walls=params.use_smoothed_side_walls,
            contour_smoothing_iterations=params.contour_smoothing_iterations,
        )
    else:
        vertices, faces = build_rectangular_relief_solid(
            heightmap,
            params.width_mm,
            params.height_mm,
            params.base_thickness_mm,
            params.relief_height_mm,
        )

    raw_vertex_count = int(len(vertices))
    raw_face_count = int(len(faces))
    vertices, faces, repair_report = repair_mesh_basic(vertices, faces)
    report = basic_report(vertices, faces, params.minimum_thickness_mm)
    report["raw_vertex_count"] = raw_vertex_count
    report["raw_face_count"] = raw_face_count
    report["optimized_vertex_count"] = raw_vertex_count
    report["optimized_face_count"] = raw_face_count
    report["mesh_optimization"] = {"mode": "indexed_builder_preserved", "global_vertex_deduplication": False}
    report["repaired_vertex_count"] = int(len(vertices))
    report["repaired_face_count"] = int(len(faces))
    report["mesh_repair"] = repair_report
    report["outline"] = outline
    report["manual_height"] = manual_height_report
    report["rim"] = rim_report
    report["side_wall_mode"] = _side_wall_mode(params)
    report["mask_mode_requested"] = str(params.mask_mode)
    report["mask_mode_used"] = resolved_mask_mode
    report["original_mask_pixel_count"] = original_mask_pixel_count
    report["mask_pixel_count"] = int(mask.sum())
    report["mask_cleanup"] = cleanup_report
    report["image_source"] = loaded_image.report()
    report["image_transform"] = image_transform.to_report()
    report["original_shape"] = original_shape
    report["shape_after_crop"] = shape_after_crop
    report["shape_after_resize"] = shape_after_resize
    report["shape_for_geometry"] = shape_for_geometry
    report["crop_box"] = crop_box
    report["geometry_crop_box"] = geometry_crop_box
    report["resize_scale"] = resize_scale
    report["downsampled"] = bool(resize_scale < 1.0)
    report["footprint_mode"] = "mask" if params.use_mask_footprint else "rectangle"
    report["preview_paths"] = preview_paths
    report["requested_size_mm"] = {"x": float(params.width_mm), "y": float(params.height_mm)}
    report["dimension_error_mm"] = {
        "x": abs(float(report["bbox"]["size_x"]) - float(params.width_mm)),
        "y": abs(float(report["bbox"]["size_y"]) - float(params.height_mm)),
    }
    report["height_clipping"] = {
        "occurred": bool(rim_report["clipped_pixel_count"] > 0),
        "rim_clipped_pixel_count": int(rim_report["clipped_pixel_count"]),
    }

    if report["mask_pixel_count"] < 4:
        report["warnings"].append("mask is very small and may produce an unusable model")
    if manual_height_report["enabled"]:
        report["warnings"].append("manual height markers were applied")
    if rim_report["enabled"]:
        report["warnings"].append("outer rim height boost was applied")
    elif effective_rim_width_px > 0 or params.rim_height_mm > 0.0:
        report["warnings"].append("outer rim was requested but not applied")
    if rim_report["clipped_pixel_count"] > 0:
        report["warnings"].append("requested rim height was clipped by the configured relief height limit")
    if cleanup_report["removed_small_component_pixels"] > 0:
        report["warnings"].append("small isolated mask fragments were removed")
    if cleanup_report["filled_hole_pixels"] > 0:
        report["warnings"].append("small mask holes were filled")
    if cleanup_report["smooth_iterations"] > 0:
        report["warnings"].append("mask smoothing was applied")
    if resize_scale < 1.0:
        report["warnings"].append("input was downsampled before mesh generation")
    if any(value > 0 for value in repair_report.values()):
        report["warnings"].append("basic mesh repair removed invalid or redundant geometry")
    if params.use_mask_footprint and params.use_smoothed_side_walls:
        report["warnings"].append("smoothed side walls were deferred to preserve a closed grid-contour solid")

    written = None
    if output_path is not None:
        blocking_errors = _blocking_topology_errors(report)
        if blocking_errors:
            raise ValueError("mesh export blocked by topology errors: " + ", ".join(blocking_errors))
        written = str(Path(output_path))
        export_mesh(written, vertices, faces)
        report["export_path"] = written
        report["export_format"] = Path(written).suffix.lower().lstrip(".")
        report["unit_convention"] = "millimeters (STL stores no explicit unit metadata)"

    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=written)
