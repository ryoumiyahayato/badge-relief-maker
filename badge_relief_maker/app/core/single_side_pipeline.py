"""Runnable single side relief pipeline for the MVP."""

from pathlib import Path

from .height_markers import apply_manual_height_markers
from .heightmap_generator import grayscale_heightmap
from .image_preprocess import load_rgba, normalize_alpha_background
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


def _side_wall_mode(params):
    if not params.use_mask_footprint:
        return "rectangle"
    return "grid_contour_closed"


def _validate_parameters(params):
    if float(params.width_mm) <= 0.0 or float(params.height_mm) <= 0.0:
        raise ValueError("width_mm and height_mm must be positive")
    if float(params.base_thickness_mm) < 0.0 or float(params.relief_height_mm) < 0.0:
        raise ValueError("base_thickness_mm and relief_height_mm must be non-negative")
    if float(params.minimum_thickness_mm) < 0.0:
        raise ValueError("minimum_thickness_mm must be non-negative")
    if int(params.crop_padding_px) < 0:
        raise ValueError("crop_padding_px must be non-negative")
    if int(params.max_grid_cells) <= 0:
        raise ValueError("max_grid_cells must be positive")


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


def build_single_side_relief(image_path, output_path=None, parameters=None, preview_dir=None):
    """Build a basic solid relief model from one image."""
    params = parameters or ReliefParameters()
    _validate_parameters(params)
    rgba = normalize_alpha_background(load_rgba(image_path))
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
    heightmap = grayscale_heightmap(rgba, mask=mask, invert=params.invert_height)
    crop_box = None
    if params.crop_to_foreground:
        mask, heightmap, crop_box = crop_to_mask(mask, heightmap, padding=params.crop_padding_px)

    shape_after_crop = tuple(mask.shape)
    mask, heightmap, resize_scale = resize_mask_and_heightmap(mask, heightmap, params.max_grid_cells)
    shape_after_resize = tuple(mask.shape)
    transformed_markers = transform_manual_height_markers(
        params.manual_height_markers,
        original_shape=original_shape,
        crop_box=crop_box,
        cropped_shape=shape_after_crop,
        resized_shape=shape_after_resize,
    )
    heightmap, manual_height_report = apply_manual_height_markers(heightmap, mask, transformed_markers)
    manual_height_report["coordinate_transform"] = "original_image_to_processed_grid"

    geometry_crop_box = None
    if params.crop_to_foreground:
        mask, heightmap, geometry_crop_box = crop_to_mask(mask, heightmap, padding=0)
    shape_for_geometry = tuple(mask.shape)

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

    # The indexed builder deliberately keeps separate vertex namespaces for
    # disconnected mask components. Global coordinate deduplication can merge
    # diagonally touching components and create non-manifold edges, so the build
    # path preserves those indices and only runs conservative face repair.
    optimized_vertex_count = raw_vertex_count
    optimized_face_count = raw_face_count
    vertices, faces, repair_report = repair_mesh_basic(vertices, faces)
    report = basic_report(vertices, faces, params.minimum_thickness_mm)
    report["raw_vertex_count"] = raw_vertex_count
    report["raw_face_count"] = raw_face_count
    report["optimized_vertex_count"] = optimized_vertex_count
    report["optimized_face_count"] = optimized_face_count
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
    report["original_shape"] = original_shape
    report["shape_after_crop"] = shape_after_crop
    report["shape_after_resize"] = shape_after_resize
    report["shape_for_geometry"] = shape_for_geometry
    report["crop_box"] = crop_box
    report["geometry_crop_box"] = geometry_crop_box
    report["resize_scale"] = resize_scale
    report["footprint_mode"] = "mask" if params.use_mask_footprint else "rectangle"
    report["preview_paths"] = preview_paths

    if report["mask_pixel_count"] == 0:
        report["warnings"].append("mask contains no foreground pixels")
    elif report["mask_pixel_count"] < 4:
        report["warnings"].append("mask is very small and may produce an unusable model")
    if manual_height_report["enabled"]:
        report["warnings"].append("manual height markers were applied")
    if rim_report["enabled"]:
        report["warnings"].append("outer rim height boost was applied")
    elif effective_rim_width_px > 0 or params.rim_height_mm > 0.0:
        report["warnings"].append("outer rim was requested but not applied")
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
        written = str(Path(output_path))
        export_mesh(written, vertices, faces)
        report["export_path"] = written
        report["export_format"] = Path(written).suffix.lower().lstrip(".")

    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=written)
