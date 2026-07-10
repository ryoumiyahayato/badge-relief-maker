"""Runnable single-side relief pipeline for the local MVP."""

from pathlib import Path

import numpy as np
from PIL import Image

from .height_markers import apply_manual_height_markers
from .height_processing import apply_region_layers, refine_heightmap
from .heightmap_generator import grayscale_heightmap
from .image_editing import apply_mask_edits, crop_rgba, rectify_perspective
from .image_preprocess import load_image, normalize_alpha_background
from .image_transform import ImageTransform
from .manufacturability_check import basic_report
from .marker_transform import transform_manual_height_markers
from .mask_generator import foreground_mask
from .mask_processing import clean_mask, crop_to_mask, resize_mask_and_heightmap
from .masked_solid_builder import build_layered_relief_solid, build_masked_relief_solid
from .mesh_exporter import export_mesh
from .mesh_repair import repair_mesh_basic
from .outline_extractor import outline_report
from .preview_exporter import save_heightmap_preview, save_mask_overlay_preview, save_mask_preview, save_source_preview
from .relief_parameters import PreparedReliefField, ReliefBuildResult, ReliefParameters
from .rim_builder import apply_outer_rim_to_heightmap
from .solid_builder import build_rectangular_relief_solid


_SUPPORTED_MASK_MODES = {"auto", "alpha", "luminance", "luminance-dark", "luminance-light"}
_SUPPORTED_RIM_PROFILES = {"flat", "linear", "smooth"}
_SUPPORTED_HEIGHT_MODES = {"grayscale", "layers", "hybrid"}
_SUPPORTED_EDGE_STYLES = {"straight", "bevel", "rounded", "sloped"}
_SUPPORTED_PROCESS_PROFILES = {"general", "fdm", "resin", "cnc", "mould"}


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
    _finite_number(params.bevel_mm, "bevel_mm", nonnegative=True)
    _finite_number(params.radius_mm, "radius_mm", nonnegative=True)
    _finite_number(params.background_depth_mm, "background_depth_mm", nonnegative=True)
    uniform_height = _finite_number(params.uniform_height_normalized, "uniform_height_normalized", nonnegative=True)
    smooth_strength = _finite_number(params.smooth_strength, "smooth_strength", nonnegative=True)
    detail_sharpness = _finite_number(params.detail_sharpness, "detail_sharpness", nonnegative=True)
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
    if str(params.height_mode).strip().lower() not in _SUPPORTED_HEIGHT_MODES:
        raise ValueError("height_mode must be 'grayscale', 'layers' or 'hybrid'")
    if str(params.edge_style).strip().lower() not in _SUPPORTED_EDGE_STYLES:
        raise ValueError("edge_style must be 'straight', 'sloped', 'bevel' or 'rounded'")
    if str(params.process_profile).strip().lower() not in _SUPPORTED_PROCESS_PROFILES:
        raise ValueError(f"unsupported process_profile: {params.process_profile}")
    if uniform_height > 1.0 or smooth_strength > 1.0 or detail_sharpness > 1.0:
        raise ValueError("uniform_height_normalized, smooth_strength and detail_sharpness must be between 0 and 1")
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


def _resize_rgba(rgba, target_shape):
    rows, cols = target_shape
    image = Image.fromarray(np.asarray(rgba, dtype=np.uint8), mode="RGBA")
    return np.asarray(image.resize((cols, rows), Image.Resampling.BILINEAR))


def _compose_crop_boxes(manual_box, automatic_box):
    if automatic_box is None:
        return manual_box
    manual_x = manual_box[0] if manual_box is not None else 0
    manual_y = manual_box[1] if manual_box is not None else 0
    x0, y0, x1, y1 = automatic_box
    return x0 + manual_x, y0 + manual_y, x1 + manual_x, y1 + manual_y


def prepare_relief_field(image_path, parameters=None, preview_dir=None):
    """Prepare the exact final-grid mask and height field without building a mesh."""
    params = parameters or ReliefParameters()
    _validate_parameters(params)
    loaded_image = load_image(image_path)
    rgba = normalize_alpha_background(loaded_image.rgba)
    rgba, perspective_report = rectify_perspective(rgba, params.perspective_quad)
    processing_shape = tuple(rgba.shape[:2])

    mask, resolved_mask_mode = foreground_mask(
        rgba,
        mode=params.mask_mode,
        alpha_threshold=params.alpha_threshold,
        luminance_threshold=params.luminance_threshold,
    )
    mask, mask_edit_report = apply_mask_edits(mask, params.manual_mask_edits)
    original_mask_pixel_count = int(mask.sum())

    manual_crop_box = None
    if params.manual_crop_box is not None:
        rgba, manual_crop_box = crop_rgba(rgba, params.manual_crop_box)
        x0, y0, x1, y1 = manual_crop_box
        mask = mask[y0:y1, x0:x1]

    mask, cleanup_report = clean_mask(
        mask,
        min_component_pixels=params.min_component_pixels,
        fill_hole_pixels=params.fill_hole_pixels,
        smooth_iterations=params.mask_smooth_iterations,
    )
    if not mask.any():
        _save_empty_previews(mask, preview_dir)
        raise ValueError("foreground mask is empty; adjust the mask mode, threshold, cleanup settings or source image")

    height_mode = str(params.height_mode).strip().lower()
    if height_mode == "layers":
        background = 0.0 if float(params.relief_height_mm) <= 0.0 else float(params.background_depth_mm) / float(params.relief_height_mm)
        heightmap = np.where(mask, np.clip(background, 0.0, 1.0), 0.0).astype(np.float32)
    else:
        heightmap = grayscale_heightmap(
            rgba,
            mask=mask,
            invert=params.invert_height,
            uniform_value=params.uniform_height_normalized,
        )

    automatic_crop_box = None
    if params.crop_to_foreground:
        mask, heightmap, automatic_crop_box = crop_to_mask(mask, heightmap, padding=params.crop_padding_px)
        if automatic_crop_box is not None:
            x0, y0, x1, y1 = automatic_crop_box
            rgba = rgba[y0:y1, x0:x1]
    crop_box = _compose_crop_boxes(manual_crop_box, automatic_crop_box)
    shape_after_crop = tuple(mask.shape)
    mask, heightmap, resize_scale = resize_mask_and_heightmap(mask, heightmap, params.max_grid_cells)
    shape_after_resize = tuple(mask.shape)
    rgba = _resize_rgba(rgba, shape_after_resize)
    image_transform = ImageTransform(
        original_shape=processing_shape,
        crop_box=crop_box,
        cropped_shape=shape_after_crop,
        resized_shape=shape_after_resize,
    )

    geometry_crop_box = None
    if params.crop_to_foreground:
        mask, heightmap, geometry_crop_box = crop_to_mask(mask, heightmap, padding=0)
        if geometry_crop_box is not None:
            x0, y0, x1, y1 = geometry_crop_box
            rgba = rgba[y0:y1, x0:x1]
    shape_for_geometry = tuple(mask.shape)
    image_transform = image_transform.with_geometry_crop(geometry_crop_box, shape_for_geometry)

    heightmap, refinement_report = refine_heightmap(
        heightmap,
        mask,
        smooth_strength=params.smooth_strength,
        detail_sharpness=params.detail_sharpness,
    )
    transformed_layers = transform_manual_height_markers(params.region_layers, image_transform=image_transform)
    heightmap, locked_pixels, layer_report = apply_region_layers(heightmap, mask, transformed_layers)
    transformed_markers = transform_manual_height_markers(params.manual_height_markers, image_transform=image_transform)
    heightmap, manual_height_report = apply_manual_height_markers(heightmap, mask & ~locked_pixels, transformed_markers)
    manual_height_report["coordinate_transform"] = "ImageTransform.original_image_to_final_geometry_grid"

    effective_rim_width_px = _effective_rim_width_px(params, mask)
    heightmap, rim_report = apply_outer_rim_to_heightmap(
        heightmap,
        mask,
        width_px=effective_rim_width_px,
        rim_height_mm=params.rim_height_mm,
        relief_height_mm=params.relief_height_mm,
        profile=params.rim_profile,
    )
    rim_report["requested_rim_width_mm"] = float(params.rim_width_mm)
    rim_report["effective_rim_width_px"] = int(effective_rim_width_px)
    cell_w_mm, cell_h_mm = image_transform.geometry_cell_size_mm(params.width_mm, params.height_mm)
    rim_report["geometry_cell_size_mm_xy"] = [cell_w_mm, cell_h_mm]
    outline = outline_report(mask, params.width_mm, params.height_mm, smoothing_iterations=params.contour_smoothing_iterations)

    preview_paths = {}
    if preview_dir is not None:
        preview_base = Path(preview_dir)
        preview_base.mkdir(parents=True, exist_ok=True)
        preview_paths["source_preview"] = save_source_preview(rgba, preview_base / "source_preview.png")
        preview_paths["mask_preview"] = save_mask_preview(mask, preview_base / "mask_preview.png")
        preview_paths["mask_overlay_preview"] = save_mask_overlay_preview(rgba, mask, preview_base / "mask_overlay_preview.png")
        preview_paths["heightmap_preview"] = save_heightmap_preview(heightmap, preview_base / "heightmap_preview.png")

    source_report = loaded_image.report()
    source_report["processing_shape_after_perspective"] = list(processing_shape)
    source_report["perspective"] = perspective_report
    report = {
        "outline": outline,
        "manual_height": manual_height_report,
        "region_layers": layer_report,
        "height_refinement": refinement_report,
        "rim": rim_report,
        "mask_mode_requested": str(params.mask_mode),
        "mask_mode_used": resolved_mask_mode,
        "height_mode": height_mode,
        "original_mask_pixel_count": original_mask_pixel_count,
        "mask_pixel_count": int(mask.sum()),
        "mask_cleanup": cleanup_report,
        "mask_edits": mask_edit_report,
        "image_source": source_report,
        "image_transform": image_transform.to_report(),
        "original_shape": processing_shape,
        "shape_after_crop": shape_after_crop,
        "shape_after_resize": shape_after_resize,
        "shape_for_geometry": shape_for_geometry,
        "manual_crop_box": manual_crop_box,
        "crop_box": crop_box,
        "geometry_crop_box": geometry_crop_box,
        "resize_scale": resize_scale,
        "downsampled": bool(resize_scale < 1.0),
        "preview_paths": preview_paths,
    }
    return PreparedReliefField(mask=mask, heightmap=heightmap, rgba=rgba, image_transform=image_transform, report=report)


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
    intersections = report.get("self_intersections") or {}
    if intersections.get("intersection_pair_count", 0) > 0:
        reasons.append("self intersections")
    return reasons


def build_single_side_relief(image_path, output_path=None, parameters=None, preview_dir=None):
    """Build a closed rough relief solid from one local image."""
    params = parameters or ReliefParameters()
    _validate_parameters(params)
    prepared = prepare_relief_field(image_path, params, preview_dir=preview_dir)
    mask = prepared.mask
    heightmap = prepared.heightmap
    field_report = prepared.report
    outline = field_report["outline"]
    manual_height_report = field_report["manual_height"]
    rim_report = field_report["rim"]
    cleanup_report = field_report["mask_cleanup"]
    effective_rim_width_px = rim_report["effective_rim_width_px"]
    resize_scale = field_report["resize_scale"]

    if params.use_mask_footprint and str(params.height_mode).lower() == "layers":
        if str(params.edge_style).lower() != "straight":
            raise ValueError("exact layered height steps currently require edge_style='straight'")
        vertices, faces = build_layered_relief_solid(
            heightmap,
            mask,
            params.width_mm,
            params.height_mm,
            params.base_thickness_mm,
            params.relief_height_mm,
        )
    elif params.use_mask_footprint:
        vertices, faces = build_masked_relief_solid(
            heightmap,
            mask,
            params.width_mm,
            params.height_mm,
            params.base_thickness_mm,
            params.relief_height_mm,
            use_smoothed_side_walls=params.use_smoothed_side_walls,
            contour_smoothing_iterations=params.contour_smoothing_iterations,
            edge_style=params.edge_style,
            bevel_mm=params.bevel_mm,
            radius_mm=params.radius_mm,
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
    report = basic_report(
        vertices,
        faces,
        params.minimum_thickness_mm,
        analysis_context={
            "mask": mask,
            "heightmap": heightmap,
            "width_mm": params.width_mm,
            "height_mm": params.height_mm,
            "base_thickness_mm": params.base_thickness_mm,
            "relief_height_mm": params.relief_height_mm,
            "construction": "indexed_heightfield",
            "edge_style": params.edge_style,
        },
        process_profile=params.process_profile,
    )
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
    report.update(field_report)
    report["footprint_mode"] = "mask" if params.use_mask_footprint else "rectangle"
    report["edge_geometry"] = {
        "style": str(params.edge_style),
        "bevel_mm": float(params.bevel_mm),
        "radius_mm": float(params.radius_mm),
    }
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
