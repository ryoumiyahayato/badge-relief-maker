"""Project save, load and asset import helpers."""

import json
import math
import os
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path

from .project_model import PROJECT_FILE_VERSION, ExportRecord, ImageRecord, MedalProject


PROJECT_SUFFIX = ".medalproj"


class ProjectFormatError(ValueError):
    """Raised when a project file cannot be safely interpreted."""


class UnsupportedProjectVersionError(ProjectFormatError):
    """Raised when a project was created by a newer unsupported format."""


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


def _project_version(data):
    raw = data.get("file_version", PROJECT_FILE_VERSION)
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise ProjectFormatError("project file_version must be an integer") from exc
    if version < 1:
        raise ProjectFormatError("project file_version must be positive")
    if version > PROJECT_FILE_VERSION:
        raise UnsupportedProjectVersionError(
            f"project file version {version} is newer than supported version {PROJECT_FILE_VERSION}"
        )
    return version


def migrate_project_data(data):
    """Return a current-version project dictionary without mutating the caller.

    Version 1 projects predate persisted visual-editing and fused-double-side
    settings. Their existing fields retain their previous meaning; new fields
    receive deterministic defaults.
    """
    if not isinstance(data, dict):
        raise ProjectFormatError("project root must be a JSON object")
    migrated = deepcopy(data)
    version = _project_version(migrated)
    if version == 1:
        for side_name, enabled in (("front_relief", True), ("back_relief", False)):
            side = migrated.get(side_name)
            if not isinstance(side, dict):
                side = {"enabled": enabled}
                migrated[side_name] = side
            side.setdefault("uniform_height_normalized", 1.0)
            side.setdefault("smooth_strength", 0.0)
            side.setdefault("detail_sharpness", 0.0)
            side.setdefault("process_profile", "general")
            side.setdefault("manual_crop_box", None)
            side.setdefault("perspective_quad", None)
            side.setdefault("mask_edits", [])
            side.setdefault("region_layers", [])
        migrated.setdefault(
            "double_side",
            {
                "enabled": False,
                "back_scale": 1.0,
                "back_rotation_deg": 0.0,
                "back_offset_x_mm": 0.0,
                "back_offset_y_mm": 0.0,
                "flip_back_horizontal": True,
                "footprint_mode": "union",
            },
        )
        migrated["file_version"] = 2
        version = 2
    if version != PROJECT_FILE_VERSION:
        raise UnsupportedProjectVersionError(
            f"project file version {version} is not supported by version {PROJECT_FILE_VERSION}"
        )
    return migrated


def _reject_non_finite_json(value, path="project"):
    """Reject NaN/Infinity anywhere in an untrusted project document."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ProjectFormatError(f"{path} contains a non-finite number")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_non_finite_json(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_non_finite_json(item, f"{path}[{index}]")


def save_project(project, path):
    """Flush and atomically save a project as JSON .medalproj."""
    if not isinstance(project, MedalProject):
        raise TypeError("project must be a MedalProject")
    version = _project_version({"file_version": project.file_version})
    if version < PROJECT_FILE_VERSION:
        project.file_version = PROJECT_FILE_VERSION
    else:
        project.file_version = version
    path = normalize_project_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_project_dirs(path)
    project.touch()

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(project.to_dict(), fh, indent=2, ensure_ascii=False, allow_nan=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return str(path)


def load_project(path):
    """Load and validate a supported .medalproj JSON file."""
    path = normalize_project_path(path)
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(f"project file contains invalid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ProjectFormatError("project root must be a JSON object")
    _reject_non_finite_json(data)
    data = migrate_project_data(data)
    project = MedalProject.from_dict(data)
    project.file_version = PROJECT_FILE_VERSION
    return project


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
    """Resolve a stored asset path and require it to stay inside project assets."""
    project_path = normalize_project_path(project_path)
    project_dir = project_path.parent.resolve()
    asset_root = asset_root_for(project_path).resolve()
    stored = Path(stored_path)
    candidate = stored.resolve() if stored.is_absolute() else (project_dir / stored).resolve()
    candidate = _assert_within(candidate, asset_root, "stored project asset escapes the project asset directory")
    if not candidate.is_file():
        raise FileNotFoundError(f"stored project asset does not exist: {candidate}")
    return candidate
