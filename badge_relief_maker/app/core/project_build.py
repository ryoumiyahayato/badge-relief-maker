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


def _side_data(project, side_name):
    if side_name == "front":
        return project.front_image, project.front_relief
    if side_name == "back":
        return project.back_image, project.back_relief
    raise ValueError(f"unsupported project side: {side_name}")


def _relief_parameters_from_project(project, side_name="front", quality_mode=None):
    """Create ReliefParameters from saved project settings."""
    _, side = _side_data(project, side_name)
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


def build_side_relief_from_project(project, project_path, side_name="front", export_format="obj", quality_mode=None, export_name=None):
    """Build one side relief for an existing project and update export history.

    Front and back are generated independently in the MVP. This supports the
    incremental workflow where a front-only project can later receive a back
    image without rebuilding project metadata from scratch.
    """
    image_record, _ = _side_data(project, side_name)
    if image_record is None:
        raise ValueError(f"project has no {side_name} image")

    project_path = Path(project_path)
    asset_root = asset_root_for(project_path)
    export_dir = asset_root / "exports"
    preview_dir = asset_root / "previews" / side_name
    export_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    export_format = str(export_format or "obj").lower().lstrip(".")
    if export_format not in {"obj", "stl"}:
        raise ValueError(f"unsupported project export format: {export_format}")

    params, resolved_quality = _relief_parameters_from_project(project, side_name=side_name, quality_mode=quality_mode)
    source_image = resolve_project_asset(project_path, image_record.path)
    name = _safe_name(export_name or project.name)
    output_path = export_dir / f"{name}_{side_name}_{resolved_quality}.{export_format}"

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


def build_front_relief_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    """Build the front relief for an existing project and update export history."""
    return build_side_relief_from_project(
        project,
        project_path,
        side_name="front",
        export_format=export_format,
        quality_mode=quality_mode,
        export_name=export_name,
    )


def build_back_relief_from_project(project, project_path, export_format="obj", quality_mode=None, export_name=None):
    """Build the back relief for an existing project and update export history."""
    return build_side_relief_from_project(
        project,
        project_path,
        side_name="back",
        export_format=export_format,
        quality_mode=quality_mode,
        export_name=export_name,
    )


def build_side_relief_from_project_file(project_path, side_name="front", export_format="obj", quality_mode=None, export_name=None):
    """Load a project, build one side relief, save project and return the result."""
    project = load_project(project_path)
    result = build_side_relief_from_project(
        project,
        project_path,
        side_name=side_name,
        export_format=export_format,
        quality_mode=quality_mode,
        export_name=export_name,
    )
    save_project(project, project_path)
    return result


def build_front_relief_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    """Load a project, build front relief, save project and return the build result."""
    return build_side_relief_from_project_file(
        project_path,
        side_name="front",
        export_format=export_format,
        quality_mode=quality_mode,
        export_name=export_name,
    )


def build_back_relief_from_project_file(project_path, export_format="obj", quality_mode=None, export_name=None):
    """Load a project, build back relief, save project and return the build result."""
    return build_side_relief_from_project_file(
        project_path,
        side_name="back",
        export_format=export_format,
        quality_mode=quality_mode,
        export_name=export_name,
    )
