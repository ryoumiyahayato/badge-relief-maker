"""Project save, load and asset import helpers."""

import json
import shutil
from pathlib import Path

from .project_model import ExportRecord, ImageRecord, MedalProject


PROJECT_SUFFIX = ".medalproj"


def normalize_project_path(path):
    """Return a project file path with .medalproj suffix."""
    path = Path(path)
    if path.suffix.lower() != PROJECT_SUFFIX:
        path = path.with_suffix(PROJECT_SUFFIX)
    return path


def asset_root_for(project_path):
    """Return the sibling asset directory for a project file."""
    project_path = normalize_project_path(project_path)
    return project_path.with_name(project_path.stem + "_assets")


def ensure_project_dirs(project_path):
    """Create resource directories used by a project."""
    root = asset_root_for(project_path)
    for name in ["images", "previews", "exports"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def create_project(name):
    """Create an in-memory project object."""
    return MedalProject(name=name)


def save_project(project, path):
    """Save a project as JSON .medalproj."""
    path = normalize_project_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_project_dirs(path)
    project.touch()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(project.to_dict(), fh, indent=2, ensure_ascii=False)
    return str(path)


def load_project(path):
    """Load a project from a .medalproj JSON file."""
    path = normalize_project_path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return MedalProject.from_dict(data)


def _safe_asset_name(role, source_path):
    source_path = Path(source_path)
    clean_stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in source_path.stem)
    return f"{role}_{clean_stem}{source_path.suffix.lower()}"


def import_image_asset(project, project_path, source_path, role, is_reference=False, quality_label="unknown", notes=""):
    """Copy an image into the project asset folder and attach it to the project."""
    project_path = normalize_project_path(project_path)
    source_path = Path(source_path)
    asset_root = ensure_project_dirs(project_path)
    target = asset_root / "images" / _safe_asset_name(role, source_path)
    shutil.copy2(source_path, target)

    record = ImageRecord(
        role=role,
        path=str(target.relative_to(project_path.parent)),
        original_path=str(source_path),
        is_reference=bool(is_reference),
        quality_label=quality_label,
        notes=notes,
    )

    if role == "front" and not is_reference:
        project.front_image = record
    elif role == "back" and not is_reference:
        project.back_image = record
        project.back_relief.enabled = True
    else:
        record.is_reference = True
        project.reference_images.append(record)

    project.touch()
    return record


def add_export_record(project, export_path, export_format, report=None, notes=""):
    """Append one export history entry to a project."""
    record = ExportRecord(
        path=str(export_path),
        export_format=str(export_format).lower(),
        notes=notes,
        report=report or {},
    )
    project.export_history.append(record)
    project.touch()
    return record


def resolve_project_asset(project_path, stored_path):
    """Resolve a stored relative asset path against the project folder."""
    stored = Path(stored_path)
    if stored.is_absolute():
        return stored
    return normalize_project_path(project_path).parent / stored
