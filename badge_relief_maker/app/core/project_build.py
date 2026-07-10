"""Project-aware build workflows."""

from pathlib import Path

import numpy as np

from .manufacturability_check import basic_report
from .mesh_exporter import export_glb_objects, export_mesh, export_obj_objects
from .project_io import add_export_record, asset_root_for, load_project, resolve_project_asset, save_project
from .quality_modes import quality_preset
from .relief_parameters import ReliefBuildResult, ReliefParameters
from .single_side_pipeline import build_single_side_relief


_HEIGHT_MARKER_TYPES = {"height", "height_override", "set_height"}
_HEIGHT_VALUE_KEYS = {"height_normalized", "normalized_height", "value", "height", "delta", "delta_height", "height_delta"}


def _safe_name(value):
    text = str(value or "project").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)
    return text or "project"


def _unique_output_path(directory, stem, export_format):
    """Return a non-existing export path so history never points to overwritten files."""
    directory = Path(directory)
    candidate = directory / f"{stem}.{export_format}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}.{export_format}"
        counter += 1
    return candidate


def _side_data(project, side_name):
    if side_name == "front":
        return project.front_image, project.front_relief
    if side_name == "back":
        return project.back_image, project.back_relief
    raise ValueError(f"unsupported project side: {side_name}")


def _number(value, name, *, positive=False, nonnegative=False):
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


def _validate_project_parameters(project):
    dimensions = project.dimensions
    width = _number(dimensions.width_mm, "width_mm", positive=True)
    height = _number(dimensions.height_mm, "height_mm", positive=True)
    total = _number(dimensions.total_thickness_mm, "total_thickness_mm", positive=True)
    base = _number(dimensions.base_thickness_mm, "base_thickness_mm", nonnegative=True)
    if total < base * 2.0:
        raise ValueError("total_thickness_mm must be at least twice base_thickness_mm")
    _number(project.front_relief.relief_height_mm, "front relief_height_mm", nonnegative=True)
    _number(project.back_relief.relief_height_mm, "back relief_height_mm", nonnegative=True)
    _number(project.edge.rim_width_mm, "rim_width_mm", nonnegative=True)
    _number(project.edge.rim_height_mm, "rim_height_mm", nonnegative=True)
    return width, height


def _rim_width_px_from_project(project, preset):
    """Use only explicit pixel width; millimeter conversion happens on the final grid."""
    del preset
    edge = project.edge
    if not bool(edge.rim_enabled):
        return 0
    return max(0, int(getattr(edge, "rim_width_px", 0)))


def _potential_height_marker(data):
    if not isinstance(data, dict) or not data:
        return False
    if not any(key in data for key in _HEIGHT_VALUE_KEYS):
        return False
    shape = str(data.get("shape", data.get("shape_type", "circle"))).lower()
    if shape in {"polygon", "poly", "freeform", "free_form"}:
        points = data.get("points", data.get("vertices", data.get("polygon_points")))
        return isinstance(points, (list, tuple)) and len(points) >= 3
    return ("x" in data or "center_x" in data) and ("y" in data or "center_y" in data)


def _manual_height_markers_from_project(project, side_name):
    """Return valid saved manual height marker data for one build side."""
    allowed_targets = {side_name, "both", "heightmap", "relief"}
    result = []
    for marker in getattr(project, "manual_markers", []):
        marker_type = str(getattr(marker, "marker_type", "")).lower()
        target = str(getattr(marker, "target", "")).lower()
        raw_data = getattr(marker, "data", {})
        if marker_type not in _HEIGHT_MARKER_TYPES or target not in allowed_targets or not _potential_height_marker(raw_data):
            continue
        data = dict(raw_data)
        data["marker_type"] = marker_type
        data["target"] = target
        result.append(data)
    return tuple(result)


def _relief_parameters_from_project(project, side_name="front", quality_mode=None):
    """Create ReliefParameters from saved project settings."""
    _, side = _side_data(project, side_name)
    mode = quality_mode or side.quality_mode
    preset = quality_preset(mode)
    edge = project.edge
    rim_enabled = bool(getattr(edge, "rim_enabled", False))
    return ReliefParameters(
        width_mm=project.dimensions.width_mm,
        height_mm=project.dimensions.height_mm,
        base_thickness_mm=project.dimensions.base_thickness_mm,
        relief_height_mm=side.relief_height_mm,
        max_grid_cells=preset["max_grid_cells"],
        min_component_pixels=preset["min_component_pixels"],
        fill_hole_pixels=preset["fill_hole_pixels"],
        mask_smooth_iterations=preset["mask_smooth_iterations"],
        use_smoothed_side_walls=bool(getattr(edge, "use_smoothed_side_walls", False)),
        contour_smoothing_iterations=int(getattr(edge, "contour_smoothing_iterations", 1)),
        rim_width_px=_rim_width_px_from_project(project, preset),
        rim_width_mm=float(getattr(edge, "rim_width_mm", 0.0)) if rim_enabled else 0.0,
        rim_height_mm=float(edge.rim_height_mm) if rim_enabled else 0.0,
        rim_profile=str(getattr(edge, "rim_profile", "flat") or "flat"),
        manual_height_markers=_manual_height_markers_from_project(project, side_name),
    ), preset["quality_mode"]


def _validate_export_format(export_format):
    export_format = str(export_format or "obj").lower().lstrip(".")
    if export_format not in {"obj", "stl", "glb"}:
        raise ValueError(f"unsupported project export format: {export_format}")
    return export_format


def _combine_meshes(meshes):
    vertices_parts = []
    faces_parts = []
    offset = 0
    for vertices, faces in meshes:
        vertices = np.asarray(vertices, dtype=float)
        faces = np.asarray(faces, dtype=np.int64)
        vertices_parts.append(vertices)
        faces_parts.append(faces + offset)
        offset += len(vertices)
    if not vertices_parts:
        return np.zeros((0, 3), dtype=float), np.zeros((0, 3), dtype=np.int64)
    return np.vstack(vertices_parts), np.vstack(faces_parts)


def _shift_z(vertices, amount):
    result = np.asarray(vertices, dtype=float).copy()
    result[:, 2] = result[:, 2] + float(amount)
    return result


def _mirror_z_mesh(vertices, faces):
    """Reflect a mesh across Z and reverse winding to preserve outward normals."""
    mirrored_vertices = np.asarray(vertices, dtype=float).copy()
    mirrored_vertices[:, 2] = -mirrored_vertices[:, 2]
    mirrored_faces = np.asarray(faces, dtype=np.int64).copy()
    if len(mirrored_faces):
        mirrored_faces = mirrored_faces[:, [0, 2, 1]]
    return mirrored_vertices, mirrored_faces


def _build_side_mesh_only(project, project_path, side_name, quality_mode, preview_root):
    image_record, _ = _side_data(project, side_name)
    if image_record is None:
        raise ValueError(f"project has no {side_name} image")
    params, resolved_quality = _relief_parameters_from_project(project, side_name=side_name, quality_mode=quality_mode)
    source_image = resolve_project_asset(project_path, image_record.path)
    preview_dir = Path(preview_root) / side_name
    return build_single_side_relief(source_image, None, params, preview_dir=preview_dir), resolved_quality


def build_side_relief_from_project(project, project_path, side_name="front", export_format="obj", quality_mode=None, export_name=None):
    """Build one side relief for an existing project and update export history."""
    _validate_project_parameters(project)
    image_record, _ = _side_data(project, side_name)
    if image_record is None:
        raise ValueError(f"project has no {side_name} image")

    project_path = Path(project_path)
    asset_root = asset_root_for(project_path)
    export_dir = asset_root / "exports"
    preview_dir = asset_root / "previews" / side_name
    export_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    export_format = _validate_export_format(export_format)
    params, resolved_quality = _relief_parameters_from_project(project, side_name=side_name, quality_mode=quality_mode)
    source_image = resolve_project_asset(project_path, image_record.path)
    name = _safe_name(export_name or project.name)
    output_path = _unique_output_path(export_dir, f"{name}_{side_name}_{resolved_quality}", export_format)

    result = build_single_side_relief(source_image, output_path, params, preview_dir=preview_dir)
    result.report["project_name"] = project.name
    result.report["project_quality_mode"] = resolved_quality
    result.report["project_source_role"] = side_name
    result.report["same_physical_object"] = project.same_physical_object

    add_export_record(
        project,
        str(output_path.relative_to(project_path.parent)),
        export_format,
        report=result.report,
        notes=f"{side_name} relief {resolved_quality}",
    )
    return result


def build_double_side_placeholder_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    """Build a placeholder double-side assembly from front and back images."""
    _validate_project_parameters(project)
    if project.front_image is None:
        raise ValueError("project has no front image")
    if project.back_image is None:
        raise ValueError("project has no back image")

    project_path = Path(project_path)
    asset_root = asset_root_for(project_path)
    export_dir = asset_root / "exports"
    preview_root = asset_root / "previews" / "double_placeholder"
    export_dir.mkdir(parents=True, exist_ok=True)
    preview_root.mkdir(parents=True, exist_ok=True)

    export_format = _validate_export_format(export_format)
    front_result, resolved_quality = _build_side_mesh_only(project, project_path, "front", quality_mode, preview_root)
    back_result, _ = _build_side_mesh_only(project, project_path, "back", quality_mode, preview_root)

    half_thickness = float(project.dimensions.total_thickness_mm) / 2.0
    front_vertices = _shift_z(front_result.vertices, half_thickness)
    mirrored_back_vertices, back_faces = _mirror_z_mesh(back_result.vertices, back_result.faces)
    back_vertices = _shift_z(mirrored_back_vertices, -half_thickness)
    split_objects = [
        {"name": "front_relief", "vertices": front_vertices, "faces": front_result.faces},
        {"name": "back_relief", "vertices": back_vertices, "faces": back_faces},
    ]
    vertices, faces = _combine_meshes([(front_vertices, front_result.faces), (back_vertices, back_faces)])

    report = basic_report(vertices, faces, minimum_thickness_mm=project.dimensions.base_thickness_mm)
    report["project_name"] = project.name
    report["project_quality_mode"] = resolved_quality
    report["project_source_role"] = "double_placeholder"
    report["assembly_mode"] = "front_back_placeholder_not_fused"
    report["same_physical_object"] = project.same_physical_object
    report["split_objects"] = [item["name"] for item in split_objects] if export_format in {"obj", "glb"} else []
    report["front_report"] = front_result.report
    report["back_report"] = back_result.report
    report["warnings"].append("double side placeholder is not fused into one watertight production body")

    name = _safe_name(export_name or project.name)
    output_path = _unique_output_path(export_dir, f"{name}_double_placeholder_{resolved_quality}", export_format)
    if export_format == "obj":
        export_obj_objects(output_path, split_objects)
    elif export_format == "glb":
        export_glb_objects(output_path, split_objects)
    else:
        export_mesh(output_path, vertices, faces)
    report["export_path"] = str(output_path)
    report["export_format"] = export_format

    add_export_record(
        project,
        str(output_path.relative_to(project_path.parent)),
        export_format,
        report=report,
        notes=f"double side placeholder {resolved_quality}",
    )
    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=str(output_path))


def build_front_relief_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    return build_side_relief_from_project(project, project_path, "front", export_format, quality_mode, export_name)


def build_back_relief_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    return build_side_relief_from_project(project, project_path, "back", export_format, quality_mode, export_name)


def build_side_relief_from_project_file(project_path, side_name="front", export_format="obj", quality_mode=None, export_name=None):
    """Load a project file and build the requested side."""
    project = load_project(project_path)
    result = build_side_relief_from_project(project, project_path, side_name, export_format, quality_mode, export_name)
    save_project(project, project_path)
    return result


def build_front_relief_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    return build_side_relief_from_project_file(project_path, "front", export_format, quality_mode, export_name)


def build_back_relief_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    return build_side_relief_from_project_file(project_path, "back", export_format, quality_mode, export_name)


def build_double_side_placeholder_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    project = load_project(project_path)
    result = build_double_side_placeholder_from_project(project, project_path, export_format, quality_mode, export_name)
    save_project(project, project_path)
    return result
