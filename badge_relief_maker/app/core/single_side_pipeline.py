"""Runnable single side relief pipeline for the MVP."""

from pathlib import Path

from .heightmap_generator import grayscale_heightmap
from .image_preprocess import load_rgba, normalize_alpha_background
from .manufacturability_check import basic_report
from .mask_generator import alpha_mask, luminance_mask
from .mesh_exporter import export_obj
from .relief_parameters import ReliefBuildResult, ReliefParameters
from .solid_builder import build_rectangular_relief_solid


def build_single_side_relief(image_path, output_path=None, parameters=None):
    """Build a basic solid relief model from one image.

    This is the first deterministic pipeline. It uses a rectangular footprint
    and should be replaced by contour based side closure later.
    """
    params = parameters or ReliefParameters()
    rgba = normalize_alpha_background(load_rgba(image_path))
    mask = alpha_mask(rgba, params.alpha_threshold)
    if not mask.any():
        mask = luminance_mask(rgba)

    heightmap = grayscale_heightmap(rgba, mask=mask, invert=params.invert_height)
    vertices, faces = build_rectangular_relief_solid(
        heightmap,
        params.width_mm,
        params.height_mm,
        params.base_thickness_mm,
        params.relief_height_mm,
    )
    report = basic_report(vertices, faces, params.minimum_thickness_mm)

    written = None
    if output_path is not None:
        written = str(Path(output_path))
        export_obj(written, vertices, faces)

    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=written)
