"""Build a closed relief only from an explicitly approved grayscale master."""

from pathlib import Path

import numpy as np
from PIL import Image

from .manufacturability_check import basic_report
from .masked_solid_builder import build_masked_relief_solid
from .mesh_exporter import export_mesh, export_obj_face_groups, single_side_surface_face_groups
from .mesh_repair import repair_mesh_basic
from .relief_parameters import ReliefBuildResult, ReliefParameters


def _load_normalized_height(path):
    image = Image.open(path)
    array = np.asarray(image)
    if image.mode == "F":
        values = array.astype(np.float32)
    elif np.issubdtype(array.dtype, np.integer):
        if image.mode.startswith("I;16") or (image.mode == "I" and int(array.max(initial=0)) <= 65535):
            maximum = 65535.0
        elif image.mode == "L":
            maximum = 255.0
        else:
            maximum = float(np.iinfo(array.dtype).max)
        values = array.astype(np.float32) / max(maximum, 1.0)
    else:
        values = array.astype(np.float32)
        maximum = float(np.nanmax(values)) if values.size else 1.0
        if maximum > 1.0:
            values /= maximum
    if values.ndim == 3:
        values = values[:, :, 0]
    if not np.isfinite(values).all():
        raise ValueError("approved heightmap contains non-finite values")
    return np.clip(values, 0.0, 1.0).astype(np.float32), image.mode


def _load_mask(path, shape, heightmap):
    if path is None:
        mask = heightmap > 0.0
    else:
        rows, cols = shape
        image = Image.open(path).convert("L").resize((cols, rows), Image.Resampling.NEAREST)
        mask = np.asarray(image, dtype=np.uint8) >= 128
    if not mask.any():
        raise ValueError("approved solid mask is empty")
    return mask


def _resize_for_mesh(heightmap, mask, max_grid_cells):
    rows, cols = heightmap.shape
    cells = rows * cols
    maximum = max(int(max_grid_cells), 1)
    if cells <= maximum:
        return heightmap, mask, 1.0
    scale = np.sqrt(maximum / float(cells))
    target_rows = max(2, int(round(rows * scale)))
    target_cols = max(2, int(round(cols * scale)))
    height_image = Image.fromarray(heightmap.astype(np.float32), mode="F").resize(
        (target_cols, target_rows), Image.Resampling.BICUBIC
    )
    mask_image = Image.fromarray((mask * 255).astype(np.uint8), mode="L").resize(
        (target_cols, target_rows), Image.Resampling.NEAREST
    )
    return (
        np.asarray(height_image, dtype=np.float32),
        np.asarray(mask_image, dtype=np.uint8) >= 128,
        scale,
    )


def build_relief_from_approved_heightmap(
    heightmap_path,
    output_path=None,
    *,
    mask_path=None,
    parameters=None,
):
    """Generate a closed mesh from the exact approved grayscale master.

    No source-image interpretation, line-art region inference, embossing or automatic
    height synthesis occurs here. The only optional transformation is documented
    mesh-grid resampling when the approved master exceeds ``max_grid_cells``.
    """
    params = parameters or ReliefParameters()
    heightmap_path = Path(heightmap_path)
    if not heightmap_path.is_file():
        raise FileNotFoundError(f"approved heightmap does not exist: {heightmap_path}")
    heightmap, source_mode = _load_normalized_height(heightmap_path)
    source_shape = tuple(heightmap.shape)
    mask = _load_mask(mask_path, source_shape, heightmap)
    heightmap = np.where(mask, heightmap, 0.0).astype(np.float32)
    heightmap, mask, resize_scale = _resize_for_mesh(heightmap, mask, params.max_grid_cells)

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
            "construction": "approved_grayscale_heightfield",
            "edge_style": params.edge_style,
        },
        process_profile=params.process_profile,
    )
    report.update(
        {
            "source_of_truth": "approved grayscale height master",
            "approved_heightmap_path": str(heightmap_path),
            "approved_mask_path": str(mask_path) if mask_path is not None else None,
            "approved_heightmap_mode": source_mode,
            "approved_heightmap_shape": list(source_shape),
            "mesh_grid_shape": list(heightmap.shape),
            "mesh_grid_resize_scale": float(resize_scale),
            "automatic_height_synthesis": False,
            "raw_vertex_count": raw_vertex_count,
            "raw_face_count": raw_face_count,
            "mesh_repair": repair_report,
            "back_surface_mode": "flat_plane",
            "assembly_mode": "approved_heightmap_closed_solid_with_flat_back",
        }
    )

    written = None
    if output_path is not None:
        written = str(Path(output_path))
        suffix = Path(written).suffix.lower().lstrip(".")
        if suffix == "obj":
            groups = single_side_surface_face_groups(vertices, faces)
            export_obj_face_groups(written, vertices, faces, groups, object_name="approved_heightmap_medal")
            report["editable_surface_groups"] = {name: int(len(indices)) for name, indices in groups.items()}
            report["editable_master"] = True
        elif suffix in {"stl", "glb"}:
            export_mesh(written, vertices, faces)
            report["editable_master"] = False
        else:
            raise ValueError("approved heightmap output must be OBJ, STL or GLB")
        report["export_path"] = written
        report["export_format"] = suffix
        report["unit_convention"] = "millimeters (STL stores no explicit unit metadata)"
    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=written)
