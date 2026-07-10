"""Project-aware build and export workflows."""

from pathlib import Path

import numpy as np

from .double_side_builder import build_fused_double_sided_relief
from .manufacturability_check import basic_report
from .mesh_exporter import export_glb_objects, export_mesh, export_obj_objects
from .mesh_repair import repair_mesh_basic
from .project_io import add_export_record, asset_root_for, load_project, resolve_project_asset, save_project
from .quality_modes import quality_preset
from .relief_parameters import ReliefBuildResult, ReliefParameters
from .single_side_pipeline import build_single_side_relief, prepare_relief_field


_HEIGHT_MARKER_TYPES = {"height", "height_override", "set_height"}
_HEIGHT_VALUE_KEYS = {
    "height_normalized",
    "normalized_height",
    "value",
    "height",
    "delta",
    "delta_height",
    "height_delta",
    "strength",
}
_SIDE_MODES = {"auto", "alpha", "luminance", "luminance-dark", "luminance-light"}
_HEIGHT_MODES = {"grayscale", "layers", "hybrid"}
_PROCESS_PROFILES = {"general", "fdm", "resin", "cnc", "mould"}
_EDGE_STYLES = {"straight", "sloped", "bevel", "rounded"}
_FOOTPRINT_MODES = {"union", "intersection", "front", "back"}


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


def _number(value, name, *, positive=False, nonnegative=False, maximum=None):
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
    if maximum is not None and result > float(maximum):
        raise ValueError(f"{name} must be at most {maximum}")
    return result


def _integer(value, name, *, minimum=None, maximum=None):
    converted = _number(value, name)
    if converted != round(converted):
        raise ValueError(f"{name} must be an integer")
    result = int(converted)
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return result


def _validate_side_parameters(side, label):
    _number(side.relief_height_mm, f"{label} relief_height_mm", nonnegative=True)
    _number(side.background_depth_mm, f"{label} background_depth_mm", nonnegative=True)
    _number(side.luminance_threshold, f"{label} luminance_threshold", nonnegative=True)
    _number(side.minimum_thickness_mm, f"{label} minimum_thickness_mm", nonnegative=True)
    _number(side.uniform_height_normalized, f"{label} uniform_height_normalized", nonnegative=True, maximum=1.0)
    _number(side.smooth_strength, f"{label} smooth_strength", nonnegative=True, maximum=1.0)
    _number(side.detail_sharpness, f"{label} detail_sharpness", nonnegative=True, maximum=1.0)
    _integer(side.alpha_threshold, f"{label} alpha_threshold", minimum=0, maximum=255)
    _integer(side.crop_padding_px, f"{label} crop_padding_px", minimum=0)
    if str(side.mask_mode).strip().lower() not in _SIDE_MODES:
        raise ValueError(f"unsupported {label} mask_mode: {side.mask_mode}")
    if str(side.height_mode).strip().lower() not in _HEIGHT_MODES:
        raise ValueError(f"unsupported {label} height_mode: {side.height_mode}")
    if str(side.process_profile).strip().lower() not in _PROCESS_PROFILES:
        raise ValueError(f"unsupported {label} process_profile: {side.process_profile}")


def _validate_double_alignment(project):
    alignment = project.double_side
    _number(alignment.back_scale, "back_scale", positive=True)
    _number(alignment.back_rotation_deg, "back_rotation_deg")
    _number(alignment.back_offset_x_mm, "back_offset_x_mm")
    _number(alignment.back_offset_y_mm, "back_offset_y_mm")
    if str(alignment.footprint_mode).strip().lower() not in _FOOTPRINT_MODES:
        raise ValueError("footprint_mode must be union, intersection, front or back")


def _validate_project_parameters(project, *, double_side=False, side_name=None, fused=False):
    """Validate dimensions and only the settings consumed by the requested build.

    ``total_thickness_mm`` is a fused-body setting and is not consumed by a
    single-side build. The non-fused placeholder is the only mode that needs
    room for two complete single-side bases.
    """
    dimensions = project.dimensions
    width = _number(dimensions.width_mm, "width_mm", positive=True)
    height = _number(dimensions.height_mm, "height_mm", positive=True)
    total = _number(dimensions.total_thickness_mm, "total_thickness_mm", positive=True)
    base = _number(dimensions.base_thickness_mm, "base_thickness_mm", nonnegative=True)
    if double_side and not fused and total < base * 2.0:
        raise ValueError("total_thickness_mm must be at least twice base_thickness_mm for a double-side placeholder")

    if double_side or fused or side_name is None:
        sides = [(project.front_relief, "front"), (project.back_relief, "back")]
    else:
        _, selected_side = _side_data(project, side_name)
        sides = [(selected_side, side_name)]
    for side, label in sides:
        _validate_side_parameters(side, label)

    edge = project.edge
    _number(edge.rim_width_mm, "rim_width_mm", nonnegative=True)
    _number(edge.rim_height_mm, "rim_height_mm", nonnegative=True)
    _number(edge.bevel_mm, "bevel_mm", nonnegative=True)
    _number(edge.radius_mm, "radius_mm", nonnegative=True)
    _integer(edge.rim_width_px, "rim_width_px", minimum=0)
    _integer(edge.contour_smoothing_iterations, "contour_smoothing_iterations", minimum=0)
    if str(edge.edge_style).strip().lower() not in _EDGE_STYLES:
        raise ValueError(f"unsupported edge_style: {edge.edge_style}")
    if fused:
        front_profile = str(project.front_relief.process_profile).strip().lower()
        back_profile = str(project.back_relief.process_profile).strip().lower()
        if front_profile != back_profile:
            raise ValueError("front and back process_profile must match for a fused build")
        _validate_double_alignment(project)
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
    operation = str(data.get("operation", data.get("mode", "set"))).lower()
    if operation not in {"smooth", "soften", "blur"} and not any(key in data for key in _HEIGHT_VALUE_KEYS):
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


def _optional_tuple(value):
    return tuple(value) if isinstance(value, (list, tuple)) else None


def _perspective_tuple(value):
    if not isinstance(value, (list, tuple)):
        return None
    try:
        return tuple(tuple(point) for point in value)
    except TypeError:
        return None


def _relief_parameters_from_project(project, side_name="front", quality_mode=None):
    """Create runtime parameters from persisted project settings."""
    _, side = _side_data(project, side_name)
    preset = quality_preset(quality_mode or side.quality_mode)
    edge = project.edge
    rim_enabled = bool(getattr(edge, "rim_enabled", False))
    return ReliefParameters(
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
        use_smoothed_side_walls=bool(getattr(edge, "use_smoothed_side_walls", False)),
        contour_smoothing_iterations=int(getattr(edge, "contour_smoothing_iterations", 1)),
        rim_width_px=_rim_width_px_from_project(project, preset),
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
        manual_height_markers=_manual_height_markers_from_project(project, side_name),
    ), preset["quality_mode"]


def relief_parameters_from_project(project, side_name="front", quality_mode=None):
    """Public validated runtime-parameter adapter used by GUI preview code."""
    _validate_project_parameters(project, side_name=side_name)
    return _relief_parameters_from_project(project, side_name, quality_mode)


def _validate_export_format(export_format):
    value = str(export_format or "obj").lower().lstrip(".")
    if value not in {"obj", "stl", "glb"}:
        raise ValueError(f"unsupported project export format: {value}")
    return value


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
    result[:, 2] += float(amount)
    return result


def _mirror_z_mesh(vertices, faces):
    """Reflect a mesh across Z and reverse winding to preserve outward normals."""
    mirrored_vertices = np.asarray(vertices, dtype=float).copy()
    mirrored_vertices[:, 2] *= -1.0
    mirrored_faces = np.asarray(faces, dtype=np.int64).copy()
    if len(mirrored_faces):
        mirrored_faces = mirrored_faces[:, [0, 2, 1]]
    return mirrored_vertices, mirrored_faces


def _build_side_mesh_only(project, project_path, side_name, quality_mode, preview_root):
    image_record, _ = _side_data(project, side_name)
    if image_record is None:
        raise ValueError(f"project has no {side_name} image")
    params, resolved_quality = _relief_parameters_from_project(project, side_name, quality_mode)
    source_image = resolve_project_asset(project_path, image_record.path)
    return build_single_side_relief(source_image, None, params, preview_dir=Path(preview_root) / side_name), resolved_quality


def _prepare_side_field(project, project_path, side_name, quality_mode, preview_root):
    image_record, _ = _side_data(project, side_name)
    if image_record is None:
        raise ValueError(f"project has no {side_name} image")
    params, resolved_quality = _relief_parameters_from_project(project, side_name, quality_mode)
    source_image = resolve_project_asset(project_path, image_record.path)
    prepared = prepare_relief_field(source_image, params, preview_dir=Path(preview_root) / side_name)
    return prepared, params, resolved_quality


def build_side_relief_from_project(project, project_path, side_name="front", export_format="obj", quality_mode=None, export_name=None):
    """Build one side relief for an existing project and update export history."""
    _validate_project_parameters(project, side_name=side_name)
    image_record, _ = _side_data(project, side_name)
    if image_record is None:
        raise ValueError(f"project has no {side_name} image")
    project_path = Path(project_path)
    export_dir = asset_root_for(project_path) / "exports"
    preview_dir = asset_root_for(project_path) / "previews" / side_name
    export_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    export_format = _validate_export_format(export_format)
    params, resolved_quality = _relief_parameters_from_project(project, side_name, quality_mode)
    source_image = resolve_project_asset(project_path, image_record.path)
    output_path = _unique_output_path(export_dir, f"{_safe_name(export_name or project.name)}_{side_name}_{resolved_quality}", export_format)
    result = build_single_side_relief(source_image, output_path, params, preview_dir=preview_dir)
    result.report.update(
        {
            "project_name": project.name,
            "project_quality_mode": resolved_quality,
            "project_source_role": side_name,
            "same_physical_object": project.same_physical_object,
            "configured_total_thickness_mm": float(project.dimensions.total_thickness_mm),
            "thickness_semantics": "single-side bbox thickness equals base plus generated relief; total thickness is the fused-body setting",
        }
    )
    add_export_record(project, str(output_path.relative_to(project_path.parent)), export_format, report=result.report, notes=f"{side_name} relief {resolved_quality}")
    return result


def build_double_side_placeholder_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    """Build two separate closed side meshes for non-production inspection."""
    _validate_project_parameters(project, double_side=True)
    if project.front_image is None or project.back_image is None:
        raise ValueError("double-side placeholder requires both front and back images")
    project_path = Path(project_path)
    export_dir = asset_root_for(project_path) / "exports"
    preview_root = asset_root_for(project_path) / "previews" / "double_placeholder"
    export_dir.mkdir(parents=True, exist_ok=True)
    preview_root.mkdir(parents=True, exist_ok=True)
    export_format = _validate_export_format(export_format)
    front_result, resolved_quality = _build_side_mesh_only(project, project_path, "front", quality_mode, preview_root)
    back_result, _ = _build_side_mesh_only(project, project_path, "back", quality_mode, preview_root)
    half_thickness = float(project.dimensions.total_thickness_mm) / 2.0
    front_vertices = _shift_z(front_result.vertices, half_thickness)
    mirrored_back, back_faces = _mirror_z_mesh(back_result.vertices, back_result.faces)
    back_vertices = _shift_z(mirrored_back, -half_thickness)
    split_objects = [
        {"name": "front_relief", "vertices": front_vertices, "faces": front_result.faces},
        {"name": "back_relief", "vertices": back_vertices, "faces": back_faces},
    ]
    vertices, faces = _combine_meshes([(front_vertices, front_result.faces), (back_vertices, back_faces)])
    report = basic_report(vertices, faces, minimum_thickness_mm=project.dimensions.base_thickness_mm)
    warning = "double side placeholder is not fused into one watertight production body"
    report.update(
        {
            "project_name": project.name,
            "project_quality_mode": resolved_quality,
            "project_source_role": "double_placeholder",
            "assembly_mode": "front_back_placeholder_not_fused",
            "same_physical_object": project.same_physical_object,
            "configured_total_thickness_mm": float(project.dimensions.total_thickness_mm),
            "thickness_semantics": "placeholder offsets two complete single-side solids and is not a final-body thickness",
            "split_objects": [item["name"] for item in split_objects] if export_format in {"obj", "glb"} else [],
            "front_report": front_result.report,
            "back_report": back_result.report,
        }
    )
    report["warnings"].append(warning)
    report["manufacturing_gate"]["status"] = "blocked"
    report["manufacturing_gate"]["topology_checks_passed"] = False
    if warning not in report["manufacturing_gate"]["blockers"]:
        report["manufacturing_gate"]["blockers"].append(warning)
    output_path = _unique_output_path(export_dir, f"{_safe_name(export_name or project.name)}_double_placeholder_{resolved_quality}", export_format)
    if export_format == "obj":
        export_obj_objects(output_path, split_objects)
    elif export_format == "glb":
        export_glb_objects(output_path, split_objects)
    else:
        export_mesh(output_path, vertices, faces)
    report.update({"export_path": str(output_path), "export_format": export_format, "unit_convention": "millimeters (STL stores no explicit unit metadata)"})
    add_export_record(project, str(output_path.relative_to(project_path.parent)), export_format, report=report, notes=f"double side placeholder {resolved_quality}")
    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=str(output_path))


def build_fused_double_side_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    """Build one aligned, fused and oriented front/back production candidate."""
    if project.front_image is None or project.back_image is None:
        raise ValueError("fused double-side mode requires both front and back images")
    _validate_project_parameters(project, fused=True)
    export_format = _validate_export_format(export_format)
    project_path = Path(project_path)
    export_dir = asset_root_for(project_path) / "exports"
    preview_root = asset_root_for(project_path) / "previews" / "double_fused"
    export_dir.mkdir(parents=True, exist_ok=True)
    preview_root.mkdir(parents=True, exist_ok=True)
    front, front_params, resolved_quality = _prepare_side_field(project, project_path, "front", quality_mode, preview_root)
    back, back_params, _ = _prepare_side_field(project, project_path, "back", quality_mode, preview_root)
    alignment_model = project.double_side
    alignment = {
        "back_scale": alignment_model.back_scale,
        "back_rotation_deg": alignment_model.back_rotation_deg,
        "back_offset_x_mm": alignment_model.back_offset_x_mm,
        "back_offset_y_mm": alignment_model.back_offset_y_mm,
        "flip_back_horizontal": alignment_model.flip_back_horizontal,
        "footprint_mode": alignment_model.footprint_mode,
    }
    vertices, faces, footprint, front_field, back_field, alignment_report = build_fused_double_sided_relief(
        front.mask,
        front.heightmap,
        back.mask,
        back.heightmap,
        project.dimensions.width_mm,
        project.dimensions.height_mm,
        project.dimensions.total_thickness_mm,
        front_params.relief_height_mm,
        back_params.relief_height_mm,
        quality_preset(resolved_quality)["max_grid_cells"],
        alignment=alignment,
        edge_style=project.edge.edge_style,
        bevel_mm=project.edge.bevel_mm,
        radius_mm=project.edge.radius_mm,
    )
    vertices, faces, repair_report = repair_mesh_basic(vertices, faces)
    combined_relief = float(front_params.relief_height_mm) + float(back_params.relief_height_mm)
    combined_height = (
        front_field * float(front_params.relief_height_mm) + back_field * float(back_params.relief_height_mm)
    ) / max(combined_relief, 1e-12)
    minimum_thickness = max(float(front_params.minimum_thickness_mm), float(back_params.minimum_thickness_mm))
    report = basic_report(
        vertices,
        faces,
        minimum_thickness,
        analysis_context={
            "mask": footprint,
            "heightmap": combined_height,
            "width_mm": project.dimensions.width_mm,
            "height_mm": project.dimensions.height_mm,
            "base_thickness_mm": project.dimensions.total_thickness_mm,
            "relief_height_mm": combined_relief,
            "construction": "indexed_heightfield",
            "edge_style": project.edge.edge_style,
        },
        process_profile=front_params.process_profile,
    )
    report.update(
        {
            "project_name": project.name,
            "project_quality_mode": resolved_quality,
            "project_source_role": "double_fused",
            "assembly_mode": "aligned_fused_double_side",
            "same_physical_object": project.same_physical_object,
            "alignment": alignment_report,
            "front_report": front.report,
            "back_report": back.report,
            "mesh_repair": repair_report,
            "process_profile": front_params.process_profile,
            "body_thickness_mm": float(project.dimensions.total_thickness_mm),
            "front_relief_height_mm": float(front_params.relief_height_mm),
            "back_relief_height_mm": float(back_params.relief_height_mm),
            "thickness_semantics": "body thickness excludes outward front and back relief heights",
            "unit_convention": "millimeters (STL stores no explicit unit metadata)",
        }
    )
    if report["components"]["component_count"] != 1:
        raise ValueError("fused double-side result must contain exactly one connected component")
    if report["manufacturing_gate"]["status"] == "blocked":
        raise ValueError("fused double-side export blocked: " + "; ".join(report["manufacturing_gate"]["blockers"]))
    output_path = _unique_output_path(export_dir, f"{_safe_name(export_name or project.name)}_double_fused_{resolved_quality}", export_format)
    export_mesh(output_path, vertices, faces)
    report.update({"export_path": str(output_path), "export_format": export_format})
    add_export_record(project, str(output_path.relative_to(project_path.parent)), export_format, report=report, notes=f"fused double-side {resolved_quality}")
    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=str(output_path))


def build_front_relief_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    return build_side_relief_from_project(project, project_path, "front", export_format, quality_mode, export_name)


def build_back_relief_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    return build_side_relief_from_project(project, project_path, "back", export_format, quality_mode, export_name)


def build_side_relief_from_project_file(project_path, side_name="front", export_format="obj", quality_mode=None, export_name=None):
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


def build_fused_double_side_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    project = load_project(project_path)
    result = build_fused_double_side_from_project(project, project_path, export_format, quality_mode, export_name)
    save_project(project, project_path)
    return result
