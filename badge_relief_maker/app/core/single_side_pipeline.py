"""Runnable single side relief pipeline for the MVP."""

from pathlib import Path

from .heightmap_generator import grayscale_heightmap
from .image_preprocess import load_rgba, normalize_alpha_background
from .manufacturability_check import basic_report
from .mask_generator import alpha_mask, luminance_mask
from .mask_processing import crop_to_mask, resize_mask_and_heightmap
from .masked_solid_builder import build_masked_relief_solid
from .mesh_exporter import export_obj
from .mesh_optimize import optimize_mesh
from .preview_exporter import save_heightmap_preview, save_mask_preview
from .relief_parameters import ReliefBuildResult, ReliefParameters
from .solid_builder import build_rectangular_relief_solid


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
    heightmap = grayscale_heightmap(rgba, mask=mask, invert=params.invert_height)
    crop_box = None
    if params.crop_to_foreground:
        mask, heightmap, crop_box = crop_to_mask(mask, heightmap, padding=params.crop_padding_px)

    shape_after_crop = tuple(mask.shape)
    mask, heightmap, resize_scale = resize_mask_and_heightmap(mask, heightmap, params.max_grid_cells)
    shape_after_resize = tuple(mask.shape)

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
    report = basic_report(vertices, faces, params.minimum_thickness_mm)
    report["raw_vertex_count"] = raw_vertex_count
    report["raw_face_count"] = raw_face_count
    report["optimized_vertex_count"] = int(len(vertices))
    report["optimized_face_count"] = int(len(faces))
    report["mask_pixel_count"] = int(mask.sum())
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
    if resize_scale < 1.0:
        report["warnings"].append("input was downsampled before mesh generation")
    if raw_vertex_count > report["optimized_vertex_count"]:
        report["warnings"].append("duplicate vertices were merged during optimization")

    written = None
    if output_path is not None:
        written = str(Path(output_path))
        export_obj(written, vertices, faces)

    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=written)
