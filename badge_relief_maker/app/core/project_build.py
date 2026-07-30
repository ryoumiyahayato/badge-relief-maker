"""Project-aware build and export workflows."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .double_side_builder import build_fused_double_sided_relief
from .manufacturability_check import basic_report
from .mesh_exporter import export_glb_objects, export_mesh, export_obj_objects
from .mesh_repair import repair_mesh_basic
from .options import EXPORT_FORMATS
from .project_parameters import (
    map_project_relief_parameters,
    project_side,
    resolve_double_quality,
    validate_project_parameters,
)
from .project_io import add_export_record, asset_root_for, load_project, resolve_project_asset, save_project
from .quality_modes import quality_preset
from .relief_parameters import ReliefBuildResult
from .single_side_pipeline import build_single_side_relief, prepare_relief_field
from .units import STL_UNIT_CONVENTION


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


@dataclass(frozen=True)
class ProjectBuildWorkspace:
    """Own all derived paths for one project build invocation."""

    project_path: Path

    def __init__(self, project_path):
        object.__setattr__(self, "project_path", Path(project_path))

    @property
    def export_dir(self):
        directory = asset_root_for(self.project_path) / "exports"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def preview_dir(self, *parts):
        directory = asset_root_for(self.project_path) / "previews"
        for part in parts:
            directory /= str(part)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def output_path(self, stem, export_format):
        return _unique_output_path(self.export_dir, stem, export_format)

    def history_path(self, output_path):
        return str(Path(output_path).relative_to(self.project_path.parent))


def _validate_export_format(export_format):
    value = str(export_format or "obj").lower().lstrip(".")
    if value not in EXPORT_FORMATS:
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
    image_record, _ = project_side(project, side_name)
    if image_record is None:
        raise ValueError(f"project has no {side_name} image")
    params, resolved_quality = map_project_relief_parameters(project, side_name, quality_mode)
    source_image = resolve_project_asset(project_path, image_record.path)
    return build_single_side_relief(source_image, None, params, preview_dir=Path(preview_root) / side_name), resolved_quality


def _prepare_side_field(project, project_path, side_name, quality_mode, preview_root):
    image_record, _ = project_side(project, side_name)
    if image_record is None:
        raise ValueError(f"project has no {side_name} image")
    params, resolved_quality = map_project_relief_parameters(project, side_name, quality_mode)
    source_image = resolve_project_asset(project_path, image_record.path)
    prepared = prepare_relief_field(source_image, params, preview_dir=Path(preview_root) / side_name)
    return prepared, params, resolved_quality


def build_side_relief_from_project(project, project_path, side_name="front", export_format="obj", quality_mode=None, export_name=None):
    """Build one side relief for an existing project and update export history."""
    validate_project_parameters(project, side_name=side_name)
    image_record, _ = project_side(project, side_name)
    if image_record is None:
        raise ValueError(f"project has no {side_name} image")
    workspace = ProjectBuildWorkspace(project_path)
    project_path = workspace.project_path
    preview_dir = workspace.preview_dir(side_name)
    export_format = _validate_export_format(export_format)
    params, resolved_quality = map_project_relief_parameters(project, side_name, quality_mode)
    source_image = resolve_project_asset(project_path, image_record.path)
    output_path = workspace.output_path(f"{_safe_name(export_name or project.name)}_{side_name}_{resolved_quality}", export_format)
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
    add_export_record(project, workspace.history_path(output_path), export_format, report=result.report, notes=f"{side_name} relief {resolved_quality}")
    return result


def build_double_side_placeholder_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    """Build two separate closed side meshes for non-production inspection."""
    validate_project_parameters(project, double_side=True)
    if project.front_image is None or project.back_image is None:
        raise ValueError("double-side placeholder requires both front and back images")
    workspace = ProjectBuildWorkspace(project_path)
    project_path = workspace.project_path
    preview_root = workspace.preview_dir("double_placeholder")
    export_format = _validate_export_format(export_format)
    build_quality = resolve_double_quality(project, quality_mode)
    front_result, resolved_quality = _build_side_mesh_only(project, project_path, "front", build_quality, preview_root)
    back_result, _ = _build_side_mesh_only(project, project_path, "back", build_quality, preview_root)
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
    output_path = workspace.output_path(f"{_safe_name(export_name or project.name)}_double_placeholder_{resolved_quality}", export_format)
    if export_format == "obj":
        export_obj_objects(output_path, split_objects)
    elif export_format == "glb":
        export_glb_objects(output_path, split_objects)
    else:
        export_mesh(output_path, vertices, faces)
    report.update({"export_path": str(output_path), "export_format": export_format, "unit_convention": STL_UNIT_CONVENTION})
    add_export_record(project, workspace.history_path(output_path), export_format, report=report, notes=f"double side placeholder {resolved_quality}")
    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=str(output_path))


def build_fused_double_side_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    """Build one aligned, fused and oriented front/back production candidate."""
    if project.front_image is None or project.back_image is None:
        raise ValueError("fused double-side mode requires both front and back images")
    validate_project_parameters(project, fused=True)
    export_format = _validate_export_format(export_format)
    workspace = ProjectBuildWorkspace(project_path)
    project_path = workspace.project_path
    preview_root = workspace.preview_dir("double_fused")
    build_quality = resolve_double_quality(project, quality_mode)
    front, front_params, resolved_quality = _prepare_side_field(project, project_path, "front", build_quality, preview_root)
    back, back_params, _ = _prepare_side_field(project, project_path, "back", build_quality, preview_root)
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
            "unit_convention": STL_UNIT_CONVENTION,
        }
    )
    if report["components"]["component_count"] != 1:
        raise ValueError("fused double-side result must contain exactly one connected component")
    if report["manufacturing_gate"]["status"] == "blocked":
        raise ValueError("fused double-side export blocked: " + "; ".join(report["manufacturing_gate"]["blockers"]))
    output_path = workspace.output_path(f"{_safe_name(export_name or project.name)}_double_fused_{resolved_quality}", export_format)
    export_mesh(output_path, vertices, faces)
    report.update({"export_path": str(output_path), "export_format": export_format})
    add_export_record(project, workspace.history_path(output_path), export_format, report=report, notes=f"fused double-side {resolved_quality}")
    return ReliefBuildResult(vertices=vertices, faces=faces, report=report, output_path=str(output_path))


def build_side_relief_from_project_file(project_path, side_name="front", export_format="obj", quality_mode=None, export_name=None):
    return _run_project_file_build(
        project_path,
        build_side_relief_from_project,
        side_name,
        export_format,
        quality_mode,
        export_name,
    )


def build_front_relief_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    return build_side_relief_from_project_file(project_path, "front", export_format, quality_mode, export_name)


def build_back_relief_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    return build_side_relief_from_project_file(project_path, "back", export_format, quality_mode, export_name)


def build_double_side_placeholder_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    return _run_project_file_build(
        project_path,
        build_double_side_placeholder_from_project,
        export_format,
        quality_mode,
        export_name,
    )


def build_fused_double_side_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    return _run_project_file_build(
        project_path,
        build_fused_double_side_from_project,
        export_format,
        quality_mode,
        export_name,
    )


def _run_project_file_build(project_path, operation, *args):
    """Load, build and save through one persistence path."""
    project = load_project(project_path)
    result = operation(project, project_path, *args)
    save_project(project, project_path)
    return result
