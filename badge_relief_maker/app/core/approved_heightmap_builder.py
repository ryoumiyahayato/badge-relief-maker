"""Build a closed deterministic relief only from approved master artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .deterministic_workflow import sha256_file
from .manufacturability_check import basic_report
from .masked_solid_builder import build_masked_relief_solid
from .mesh_exporter import export_mesh
from .mesh_repair import repair_mesh_basic
from .relief_parameters import ReliefBuildResult, ReliefParameters


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_normalized_height(path: Path, *, allow_8bit_preview: bool = False) -> tuple[np.ndarray, dict]:
    with Image.open(path) as image:
        image.load()
        mode = image.mode
        array = np.asarray(image)

    if array.ndim != 2:
        raise ValueError("approved height master must be a single-channel 16-bit PNG or 32-bit float TIFF")
    if array.size == 0:
        raise ValueError("approved height master is empty")

    storage = "unknown"
    formal_precision_bits = None
    if mode == "F" or np.issubdtype(array.dtype, np.floating):
        values = array.astype(np.float64)
        storage = "32-bit floating point"
        formal_precision_bits = 32
    elif mode.startswith("I;16") or (array.dtype == np.uint16):
        values = array.astype(np.float64) / 65535.0
        storage = "16-bit unsigned integer"
        formal_precision_bits = 16
    elif mode == "I" and np.issubdtype(array.dtype, np.integer):
        maximum = int(array.max(initial=0))
        minimum = int(array.min(initial=0))
        if 0 <= minimum and maximum <= 65535:
            values = array.astype(np.float64) / 65535.0
            storage = "16-bit integer container"
            formal_precision_bits = 16
        else:
            raise ValueError("integer approved height master values must be in the unsigned 16-bit range")
    elif mode == "L" or array.dtype == np.uint8:
        if not allow_8bit_preview:
            raise ValueError(
                "8-bit images are display previews, not approved height masters; use height_master_16bit.png or height_master_32bit.tiff"
            )
        values = array.astype(np.float64) / 255.0
        storage = "8-bit preview accepted by explicit override"
        formal_precision_bits = 8
    else:
        raise ValueError("approved height master must be a single-channel 16-bit PNG or 32-bit float TIFF")

    if not np.isfinite(values).all():
        raise ValueError("approved height master contains NaN or Inf")
    clipped_low = int(np.count_nonzero(values < 0.0))
    clipped_high = int(np.count_nonzero(values > 1.0))
    values = np.clip(values, 0.0, 1.0).astype(np.float32)
    return values, {
        "mode": mode,
        "dtype": str(array.dtype),
        "storage": storage,
        "formal_precision_bits": formal_precision_bits,
        "clipped_below_zero_count": clipped_low,
        "clipped_above_one_count": clipped_high,
    }


def _load_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    if path is None:
        raise ValueError("--approved-solid-mask is required; height values never determine material existence")
    with Image.open(path) as image:
        image.load()
        array = np.asarray(image.convert("L"), dtype=np.uint8)
    if array.shape != shape:
        raise ValueError(
            f"approved solid mask shape {array.shape} does not match approved height master shape {shape}; "
            "resave aligned approved artifacts instead of silently resizing them"
        )
    mask = array >= 128
    if not mask.any():
        raise ValueError("approved solid mask is empty")
    return mask


def _resize_for_mesh(heightmap: np.ndarray, mask: np.ndarray, max_grid_cells: int):
    rows, cols = heightmap.shape
    cells = rows * cols
    maximum = max(int(max_grid_cells), 4)
    if cells <= maximum:
        return heightmap, mask, {
            "downsampled": False,
            "linear_scale": 1.0,
            "source_shape": [int(rows), int(cols)],
            "target_shape": [int(rows), int(cols)],
            "height_interpolation": "none",
            "mask_interpolation": "none",
        }
    scale = np.sqrt(maximum / float(cells))
    target_rows = max(2, int(np.floor(rows * scale)))
    target_cols = max(2, int(np.floor(cols * scale)))
    while target_rows * target_cols > maximum and (target_rows > 2 or target_cols > 2):
        if target_cols >= target_rows and target_cols > 2:
            target_cols -= 1
        elif target_rows > 2:
            target_rows -= 1
        else:
            break
    height_image = Image.fromarray(heightmap.astype(np.float32), mode="F").resize(
        (target_cols, target_rows), Image.Resampling.BICUBIC
    )
    mask_image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(
        (target_cols, target_rows), Image.Resampling.NEAREST
    )
    resized_height = np.asarray(height_image, dtype=np.float32)
    resized_mask = np.asarray(mask_image, dtype=np.uint8) >= 128
    if not resized_mask.any():
        raise ValueError("approved solid mask became empty at the selected mesh quality")
    resized_height = np.where(resized_mask, np.clip(resized_height, 0.0, 1.0), 0.0).astype(np.float32)
    if not np.isfinite(resized_height).all():
        raise ValueError("height resampling produced non-finite values")
    return resized_height, resized_mask, {
        "downsampled": True,
        "linear_scale": float(min(target_rows / rows, target_cols / cols)),
        "source_shape": [int(rows), int(cols)],
        "target_shape": [int(target_rows), int(target_cols)],
        "height_interpolation": "bicubic",
        "mask_interpolation": "nearest-neighbor binary threshold",
    }


def _foreground_extent(mask: np.ndarray) -> tuple[int, int]:
    rows, cols = np.nonzero(mask)
    if not len(rows):
        return 0, 0
    return int(rows.max() - rows.min() + 1), int(cols.max() - cols.min() + 1)


def _mesh_digest(vertices: np.ndarray, faces: np.ndarray, settings: dict) -> str:
    digest = hashlib.sha256()
    stable_vertices = np.asarray(vertices, dtype="<f8")
    stable_faces = np.asarray(faces, dtype="<i8")
    digest.update(stable_vertices.tobytes(order="C"))
    digest.update(stable_faces.tobytes(order="C"))
    digest.update(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


def _sampling_report(
    source_mask: np.ndarray,
    mesh_mask: np.ndarray,
    width_mm: float,
    height_mm: float,
    min_feature_mm: float | None,
    downsample_report: dict,
    vertex_count: int,
    face_count: int,
) -> dict:
    source_rows, source_cols = _foreground_extent(source_mask)
    mesh_rows, mesh_cols = _foreground_extent(mesh_mask)
    source_spacing_x = float(width_mm) / max(source_cols, 1)
    source_spacing_y = float(height_mm) / max(source_rows, 1)
    mesh_spacing_x = float(width_mm) / max(mesh_cols, 1)
    mesh_spacing_y = float(height_mm) / max(mesh_rows, 1)
    target_feature = None if min_feature_mm is None else float(min_feature_mm)
    suggested_spacing = None if target_feature is None else target_feature / 3.0
    resolves_requested = None
    if suggested_spacing is not None:
        resolves_requested = max(mesh_spacing_x, mesh_spacing_y) <= suggested_spacing + 1e-12
    estimated_bytes = int(vertex_count * 3 * 8 + face_count * 3 * 8)
    return {
        "source_physical_pixel_mm": {"x": source_spacing_x, "y": source_spacing_y},
        "final_grid_spacing_mm": {"x": mesh_spacing_x, "y": mesh_spacing_y},
        "source_foreground_grid": {"rows": source_rows, "columns": source_cols},
        "mesh_foreground_grid": {"rows": mesh_rows, "columns": mesh_cols},
        "mesh_array_shape": list(mesh_mask.shape),
        "grid_cell_count": int(mesh_mask.size),
        "vertex_count": int(vertex_count),
        "triangle_count": int(face_count),
        "downsampled": bool(downsample_report["downsampled"]),
        "exceeds_source_information_limit": False,
        "minimum_feature_mm": target_feature,
        "three_sample_recommended_spacing_mm": suggested_spacing,
        "requested_minimum_feature_resolved_by_grid": resolves_requested,
        "estimated_mesh_array_memory_bytes": estimated_bytes,
        "estimated_mesh_array_memory_mib": estimated_bytes / (1024.0 * 1024.0),
        "rule": "a retained minimum feature should span about three sampling units",
    }


def build_relief_from_approved_heightmap(
    heightmap_path,
    output_path=None,
    *,
    mask_path=None,
    parameters=None,
    quality_mode: str = "standard",
    min_feature_mm: float | None = None,
    report_path: str | Path | None = None,
    allow_8bit_preview: bool = False,
):
    """Generate a closed regular-grid mesh from approved mask and height artifacts.

    This function never opens or interprets the original source image. It does not
    run background detection, semantic classification, line-art interpretation,
    adaptive meshing or any automatic height synthesis. Binary mask and continuous
    height data are resampled independently only when the configured regular-grid
    cell limit requires downsampling.
    """
    params = parameters or ReliefParameters()
    heightmap_path = Path(heightmap_path)
    mask_path = Path(mask_path) if mask_path is not None else None
    if not heightmap_path.is_file():
        raise FileNotFoundError(f"approved height master does not exist: {heightmap_path}")
    if mask_path is None or not mask_path.is_file():
        raise FileNotFoundError(f"approved solid mask does not exist: {mask_path}")
    if float(params.width_mm) <= 0.0 or float(params.height_mm) <= 0.0:
        raise ValueError("width_mm and height_mm must be positive")
    if float(params.base_thickness_mm) < 0.0 or float(params.relief_height_mm) < 0.0:
        raise ValueError("base_mm and relief_mm must be non-negative")
    if min_feature_mm is not None and (not np.isfinite(min_feature_mm) or float(min_feature_mm) <= 0.0):
        raise ValueError("min_feature_mm must be a positive finite value")

    heightmap, height_metadata = _load_normalized_height(heightmap_path, allow_8bit_preview=allow_8bit_preview)
    source_shape = tuple(heightmap.shape)
    source_mask = _load_mask(mask_path, source_shape)
    source_height = np.where(source_mask, heightmap, 0.0).astype(np.float32)
    mesh_height, mesh_mask, downsample_report = _resize_for_mesh(source_height, source_mask, params.max_grid_cells)

    vertices, faces = build_masked_relief_solid(
        mesh_height,
        mesh_mask,
        params.width_mm,
        params.height_mm,
        params.base_thickness_mm,
        params.relief_height_mm,
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
            "mask": mesh_mask,
            "heightmap": mesh_height,
            "width_mm": params.width_mm,
            "height_mm": params.height_mm,
            "base_thickness_mm": params.base_thickness_mm,
            "relief_height_mm": params.relief_height_mm,
            "construction": "indexed_heightfield",
            "edge_style": params.edge_style,
        },
        process_profile=params.process_profile,
    )
    input_hashes = {
        "approved_height_master_sha256": sha256_file(heightmap_path),
        "approved_solid_mask_sha256": sha256_file(mask_path),
    }
    deterministic_settings = {
        "width_mm": float(params.width_mm),
        "height_mm": float(params.height_mm),
        "base_thickness_mm": float(params.base_thickness_mm),
        "relief_height_mm": float(params.relief_height_mm),
        "minimum_thickness_mm": float(params.minimum_thickness_mm),
        "max_grid_cells": int(params.max_grid_cells),
        "quality_mode": str(quality_mode),
        "edge_style": str(params.edge_style),
        "bevel_mm": float(params.bevel_mm),
        "radius_mm": float(params.radius_mm),
        "process_profile": str(params.process_profile),
        "min_feature_mm": None if min_feature_mm is None else float(min_feature_mm),
    }
    sampling = _sampling_report(
        source_mask,
        mesh_mask,
        params.width_mm,
        params.height_mm,
        min_feature_mm,
        downsample_report,
        len(vertices),
        len(faces),
    )
    expected_z = float(params.base_thickness_mm + params.relief_height_mm)
    report.update(
        {
            "workflow": "deterministic_grayscale_relief",
            "status": "approved_build_complete",
            "review_required": False,
            "source_of_truth": ["approved solid_mask", "approved height_master"],
            "source_image_used_for_mesh": False,
            "automatic_height_synthesis": False,
            "background_detection": False,
            "semantic_inference": False,
            "automatic_line_interpretation": False,
            "adaptive_mesh_used": False,
            "regular_shared_vertex_grid": True,
            "approved_heightmap_path": str(heightmap_path),
            "approved_mask_path": str(mask_path),
            "input_hashes": input_hashes,
            "approved_heightmap_metadata": height_metadata,
            "approved_artifact_shape": list(source_shape),
            "mesh_grid_shape": list(mesh_height.shape),
            "resampling": downsample_report,
            "sampling": sampling,
            "dimensions": {
                "requested_width_mm": float(params.width_mm),
                "requested_height_mm": float(params.height_mm),
                "base_thickness_mm": float(params.base_thickness_mm),
                "relief_height_mm": float(params.relief_height_mm),
                "expected_max_total_thickness_mm": expected_z,
                "actual_width_mm": float(report["bbox"]["size_x"]),
                "actual_height_mm": float(report["bbox"]["size_y"]),
                "actual_total_thickness_mm": float(report["bbox"]["size_z"]),
                "width_error_mm": float(report["bbox"]["size_x"] - params.width_mm),
                "height_error_mm": float(report["bbox"]["size_y"] - params.height_mm),
            },
            "height_formula": "top_z_mm = height_master * relief_height_mm; bottom_z_mm = -base_thickness_mm",
            "quality_mode": str(quality_mode),
            "deterministic_settings": deterministic_settings,
            "raw_vertex_count": raw_vertex_count,
            "raw_face_count": raw_face_count,
            "mesh_repair": repair_report,
            "back_surface_mode": "flat_plane",
            "assembly_mode": "approved_mask_and_height_closed_regular_grid_solid",
            "unit_convention": "millimeters (STL stores no explicit unit metadata)",
            "luminance_is_depth": False,
            "manufacturing_notice": "Automated checks do not replace Blender, slicer, CAM or physical manufacturing acceptance.",
        }
    )
    report["deterministic_mesh_sha256"] = _mesh_digest(vertices, faces, deterministic_settings)

    written = None
    if output_path is not None:
        output = Path(output_path)
        suffix = output.suffix.lower().lstrip(".")
        if suffix not in {"obj", "stl", "glb"}:
            raise ValueError("approved height master output must be OBJ, STL or GLB")
        output.parent.mkdir(parents=True, exist_ok=True)
        export_mesh(output, vertices, faces)
        report["editable_master"] = False
        report["surface_grouping"] = "current main atomic exporter does not add legacy OBJ face groups"
        written = str(output)
        report["export_path"] = written
        report["export_format"] = suffix
        report["output_sha256"] = sha256_file(output)
        target_report_path = Path(report_path) if report_path is not None else output.parent / "build_report.json"
        report["build_report_path"] = str(target_report_path)
        _atomic_json(target_report_path, report)
    elif report_path is not None:
        target_report_path = Path(report_path)
        report["build_report_path"] = str(target_report_path)
        _atomic_json(target_report_path, report)

    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=written)
