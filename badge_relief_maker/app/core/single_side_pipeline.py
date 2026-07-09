"""Runnable single side relief pipeline for the MVP."""

from pathlib import Path

from .heightmap_generator import grayscale_heightmap
from .image_preprocess import load_rgba, normalize_alpha_background
from .manufacturability_check import basic_report
from .mask_generator import alpha_mask, luminance_mask
from .mask_processing import clean_mask, crop_to_mask, resize_mask_and_heightmap
from .masked_solid_builder import build_masked_relief_solid
from .mesh_exporter import export_mesh
from .mesh_optimize import optimize_mesh
from .mesh_repair import repair_mesh_basic
from .outline_extractor import outline_report
from .preview_exporter import save_heightmap_preview, save_mask_preview
from .relief_parameters import ReliefBuildResult, ReliefParameters
from .rim_builder import apply_outer_rim_to_heightmap
from .solid_builder import build_rectangular_relief_solid


def _side_wall_mode(params):
    if not params.use_mask_footprint:
        return "rectangle"
    if params.use_smoothed_side_walls:
        return "smoothed_contour"
    return "grid_contour"


def build_single_side_relief(image_path, output_path=None, parameters=None, preview_dir=None):
    """Build a basic solid relief model from one image.

    The default path follows the foreground mask so transparent or dark
    background areas do not become part of the exported body. A rectangular
    fallback remains available for debugging.
    """
    params = parameters or ReliefParameters()
    rgba = normalize_alpha_background(load_rgba(image_path))
    mask = alpha_mask(rgba, params.alpha_threshold)
    if not mask.any():
        mask = luminance_mask(rgba)

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
    heightmap, rim_report = apply_outer_rim_to_heightmap(
        heightmap,
        mask,
        width_px=params.rim_width_px,
        rim_height_mm=params.rim_height_mm,
        relief_height_mm=params.relief_height_mm,
    )
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
    vertices, faces = optimize_mesh(vertices, faces)
    optimized_vertex_count = int(len(vertices))
    optimized_face_count = int(len(faces))
    vertices, faces, repair_report = repair_mesh_basic(vertices, faces)
    report = basic_report(vertices, faces, params.minimum_thickness_mm)
    report["raw_vertex_count"] = raw_vertex_count
    report["raw_face_count"] = raw_face_count
    report["optimized_vertex_count"] = optimized_vertex_count
    report["optimized_face_count"] = optimized_face_count
    report["repaired_vertex_count"] = int(len(vertices))
    report["repaired_face_count"] = int(len(faces))
    report["mesh_repair"] = repair_report
    report["outline"] = outline
    report["rim"] = rim_report
    report["side_wall_mode"] = _side_wall_mode(params)
    report["original_mask_pixel_count"] = original_mask_pixel_count
    report["mask_pixel_count"] = int(mask.sum())
    report["mask_cleanup"] = cleanup_report
    report["original_shape"] = original_shape
    report["shape_after_crop"] = shape_after_crop
    report["shape_after_resize"] = shape_after_resize
    report["crop_box"] = crop_box
    report["resize_scale"] = resize_scale
    report["footprint_mode"] = "mask" if params.use_mask_footprint else "rectangle"
    report["preview_paths"] = preview_paths

    if report["mask_pixel_count"] == 0:
        report["warnings"].append("mask contains no foreground pixels")
    elif report["mask_pixel_count"] < 4:
        report["warnings"].append("mask is very small and may produce an unusable model")
    if rim_report["enabled"]:
        report["warnings"].append("outer rim height boost was applied")
    elif params.rim_width_px > 0 or params.rim_height_mm > 0.0:
        report["warnings"].append("outer rim was requested but not applied")
    if cleanup_report["removed_small_component_pixels"] > 0:
        report["warnings"].append("small isolated mask fragments were removed")
    if cleanup_report["filled_hole_pixels"] > 0:
        report["warnings"].append("small mask holes were filled")
    if cleanup_report["smooth_iterations"] > 0:
        report["warnings"].append("mask smoothing was applied")
    if resize_scale < 1.0:
        report["warnings"].append("input was downsampled before mesh generation")
    if raw_vertex_count > optimized_vertex_count:
        report["warnings"].append("duplicate vertices were merged during optimization")
    if any(value > 0 for value in repair_report.values()):
        report["warnings"].append("basic mesh repair removed invalid or redundant geometry")
    if params.use_mask_footprint and params.use_smoothed_side_walls:
        report["warnings"].append("smoothed contour side walls are experimental and may need Blender cleanup")

    written = None
    if output_path is not None:
        written = str(Path(output_path))
        export_mesh(written, vertices, faces)
        report["export_path"] = written
        report["export_format"] = Path(written).suffix.lower().lstrip(".")

    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=written)
