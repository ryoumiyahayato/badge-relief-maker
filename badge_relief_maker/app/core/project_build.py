"""Project-aware build workflows."""

from pathlib import Path

from .project_io import add_export_record, asset_root_for, load_project, resolve_project_asset, save_project
from .quality_modes import quality_preset
from .relief_parameters import ReliefParameters
from .single_side_pipeline import build_single_side_relief


def _safe_name(value):
    text = str(value or "project").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)
    return text or "project"


def _relief_parameters_from_project(project, quality_mode=None):
    """Create ReliefParameters from saved project settings."""
    side = project.front_relief
    mode = quality_mode or side.quality_mode
    preset = quality_preset(mode)
    return ReliefParameters(
        width_mm=project.dimensions.width_mm,
        height_mm=project.dimensions.height_mm,
        base_thickness_mm=project.dimensions.base_thickness_mm,
        relief_height_mm=side.relief_height_mm,
        max_grid_cells=preset["max_grid_cells"],
        min_component_pixels=preset["min_component_pixels"],
        fill_hole_pixels=preset["fill_hole_pixels"],
        mask_smooth_iterations=preset["mask_smooth_iterations"],
    ), preset["quality_mode"]


def build_front_relief_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    """Build the front relief for an existing project and update export history."""
    if project.front_image is None:
        raise ValueError("project has no front image")

    project_path = Path(project_path)
    asset_root = asset_root_for(project_path)
    export_dir = asset_root / "exports"
    preview_dir = asset_root / "previews" / "front"
    export_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    export_format = str(export_format or "obj").lower().lstrip(".")
    if export_format not in {"obj", "stl"}:
        raise ValueError(f"unsupported project export format: {export_format}")

    params, resolved_quality = _relief_parameters_from_project(project, quality_mode=quality_mode)
    source_image = resolve_project_asset(project_path, project.front_image.path)
    name = _safe_name(export_name or project.name)
    output_path = export_dir / f"{name}_front_{resolved_quality}.{export_format}"

    result = build_single_side_relief(source_image, output_path, params, preview_dir=preview_dir)
    result.report["project_name"] = project.name
    result.report["project_quality_mode"] = resolved_quality
    result.report["project_source_role"] = "front"

    add_export_record(
        project,
        str(output_path.relative_to(project_path.parent)),
        export_format,
        report=result.report,
        notes=f"front relief {resolved_quality}",
    )
    return result


def build_front_relief_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    """Load a project, build front relief, save project and return the build result."""
    project = load_project(project_path)
    result = build_front_relief_from_project(
        project,
        project_path,
        export_format=export_format,
        quality_mode=quality_mode,
        export_name=export_name,
    )
    save_project(project, project_path)
    return result
