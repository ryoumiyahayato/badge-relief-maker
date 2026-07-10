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
    """Atomically save a project as JSON .medalproj."""
    path = normalize_project_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_project_dirs(path)
    project.touch()
    temporary_path = path.with_name(path.name + ".tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as fh:
            json.dump(project.to_dict(), fh, indent=2, ensure_ascii=False)
            fh.flush()
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return str(path)


def load_project(path):
    """Load a project from a .medalproj JSON file."""
    path = normalize_project_path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return MedalProject.from_dict(data)


def _safe_token(value, default="asset"):
    text = str(value or "").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)
    text = text.strip("._-")
    return text or default


def _safe_asset_name(role, source_path):
    source_path = Path(source_path)
    clean_role = _safe_token(role, "reference")
    clean_stem = _safe_token(source_path.stem, "image")
    suffix = source_path.suffix.lower() or ".img"
    return f"{clean_role}_{clean_stem}{suffix}"


def _unique_asset_target(images_dir, filename):
    candidate = images_dir / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while candidate.exists():
        candidate = images_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def _assert_within(path, parent, message):
    resolved_path = Path(path).resolve()
    resolved_parent = Path(parent).resolve()
    try:
        resolved_path.relative_to(resolved_parent)
    except ValueError as exc:
        raise ValueError(message) from exc
    return resolved_path


def import_image_asset(project, project_path, source_path, role, is_reference=False, quality_label="unknown", notes=""):
    """Copy an image into the project asset folder and attach it to the project."""
    project_path = normalize_project_path(project_path)
    source_path = Path(source_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"image asset does not exist: {source_path}")

    role_text = str(role or "reference").strip().lower()
    safe_role = role_text if role_text in {"front", "back"} else _safe_token(role_text, "reference")
    asset_root = ensure_project_dirs(project_path)
    images_dir = (asset_root / "images").resolve()
    target = _unique_asset_target(images_dir, _safe_asset_name(safe_role, source_path))
    target = _assert_within(target, images_dir, "asset target escapes the project images directory")
    shutil.copy2(source_path, target)

    record = ImageRecord(
        role=safe_role,
        path=str(target.relative_to(project_path.parent.resolve())),
        original_path=str(source_path),
        is_reference=bool(is_reference),
        quality_label=quality_label,
        notes=notes,
    )

    if safe_role == "front" and not is_reference:
        project.front_image = record
    elif safe_role == "back" and not is_reference:
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
    """Resolve a stored asset path while rejecting paths outside the project folder."""
    project_dir = normalize_project_path(project_path).parent.resolve()
    stored = Path(stored_path)
    candidate = stored.resolve() if stored.is_absolute() else (project_dir / stored).resolve()
    return _assert_within(candidate, project_dir, "stored project asset escapes the project directory")
