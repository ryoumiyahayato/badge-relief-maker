"""Deterministic mask and grayscale-height workflow.

This module is the simple production path.  It deliberately does not import the
semantic, confidence, Bezier or adaptive-mesh modules.  Source pixels are used
only to draft a binary material mask and a normalized height master.  Once those
artifacts are confirmed, downstream mesh generation consumes only the saved mask
and height master.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .height_markers import apply_manual_height_markers


SOLID_MODES = ("whole_plate", "auto_background", "custom")
HEIGHT_MODES = ("bright_high", "dark_high", "line_engrave", "line_emboss", "fixed")
HEIGHT_OPERATION_ORDER = (
    "automatic_height_draft",
    "global_levels",
    "line_relief",
    "region_fixed_height",
    "local_manual_edits",
    "final_confirmation",
)


@dataclass(frozen=True)
class SourceImageData:
    """Normalized source channels plus an 8-bit aligned reference image."""

    rgb: np.ndarray
    alpha: np.ndarray
    luminance: np.ndarray
    rgba8: np.ndarray
    source_mode: str
    source_dtype: str
    source_path: str | None


@dataclass(frozen=True)
class SolidMaskDraft:
    mask: np.ndarray
    report: dict


@dataclass(frozen=True)
class HeightMasterDraft:
    height_master: np.ndarray
    line_mask: np.ndarray
    report: dict


@dataclass(frozen=True)
class WorkflowArtifacts:
    paths: dict
    report: dict
    project: dict


@dataclass(frozen=True)
class LoadedWorkflowArtifacts:
    source: SourceImageData
    solid_mask: np.ndarray
    height_master: np.ndarray
    project: dict
    project_path: str


def sha256_file(path: str | Path) -> str:
    """Return a lowercase SHA-256 digest for one file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_scale(array: np.ndarray, source_mode: str) -> np.ndarray:
    values = np.asarray(array)
    if np.issubdtype(values.dtype, np.integer):
        if source_mode.startswith("I;16"):
            maximum = 65535.0
        elif source_mode == "I" and values.size and int(np.nanmax(values)) <= 65535:
            maximum = 65535.0
        else:
            maximum = float(np.iinfo(values.dtype).max)
        result = values.astype(np.float64) / max(maximum, 1.0)
    else:
        result = values.astype(np.float64)
        finite = result[np.isfinite(result)]
        if finite.size:
            maximum = float(finite.max())
            minimum = float(finite.min())
            if maximum > 1.0 or minimum < 0.0:
                # Float TIFFs are commonly either normalized or stored in an
                # integer-like range.  Preserve zero and scale only when needed.
                scale = 65535.0 if 1.0 < maximum <= 65535.0 and minimum >= 0.0 else max(maximum, 1.0)
                result = result / scale
    return np.clip(result, 0.0, 1.0)


def load_source_image(source: str | Path | Image.Image | np.ndarray) -> SourceImageData:
    """Load 8/16-bit grayscale, RGB or RGBA data without collapsing 16-bit tone."""
    source_path = None
    if isinstance(source, (str, Path)):
        source_path = str(Path(source))
        with Image.open(source) as image:
            image.load()
            source_mode = image.mode
            array = np.asarray(image)
    elif isinstance(source, Image.Image):
        source_mode = source.mode
        array = np.asarray(source)
    else:
        array = np.asarray(source)
        source_mode = "array"

    if array.ndim not in {2, 3} or array.size == 0:
        raise ValueError("source image must be a non-empty grayscale, RGB or RGBA array")
    if not np.isfinite(array.astype(np.float64, copy=False)).all():
        raise ValueError("source image contains non-finite values")

    scaled = _finite_scale(array, source_mode)
    if scaled.ndim == 2:
        rgb = np.repeat(scaled[:, :, None], 3, axis=2)
        alpha = np.ones(scaled.shape, dtype=np.float64)
    else:
        channels = scaled.shape[2]
        if channels == 1:
            rgb = np.repeat(scaled[:, :, :1], 3, axis=2)
            alpha = np.ones(scaled.shape[:2], dtype=np.float64)
        elif channels == 2:
            rgb = np.repeat(scaled[:, :, :1], 3, axis=2)
            alpha = scaled[:, :, 1]
        elif channels == 3:
            rgb = scaled[:, :, :3]
            alpha = np.ones(scaled.shape[:2], dtype=np.float64)
        else:
            rgb = scaled[:, :, :3]
            alpha = scaled[:, :, 3]

    luminance = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    rgba8 = np.dstack((np.round(rgb * 255.0).astype(np.uint8), np.round(alpha * 255.0).astype(np.uint8)))
    return SourceImageData(
        rgb=rgb.astype(np.float32),
        alpha=alpha.astype(np.float32),
        luminance=luminance.astype(np.float32),
        rgba8=rgba8,
        source_mode=str(source_mode),
        source_dtype=str(array.dtype),
        source_path=source_path,
    )


def _border_values(values: np.ndarray) -> np.ndarray:
    if values.ndim == 2:
        return np.concatenate((values[0], values[-1], values[:, 0], values[:, -1]))
    return np.concatenate((values[0], values[-1], values[:, 0], values[:, -1]), axis=0)


def _connected_from_seeds(candidates: np.ndarray, seeds: Iterable[tuple[int, int]]) -> np.ndarray:
    candidates = np.asarray(candidates, dtype=bool)
    rows, cols = candidates.shape
    connected = np.zeros_like(candidates)
    queue: deque[tuple[int, int]] = deque()
    for row, col in seeds:
        row = int(row)
        col = int(col)
        if 0 <= row < rows and 0 <= col < cols and candidates[row, col] and not connected[row, col]:
            connected[row, col] = True
            queue.append((row, col))
    while queue:
        row, col = queue.popleft()
        for next_row, next_col in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if 0 <= next_row < rows and 0 <= next_col < cols:
                if candidates[next_row, next_col] and not connected[next_row, next_col]:
                    connected[next_row, next_col] = True
                    queue.append((next_row, next_col))
    return connected


def _border_seeds(shape: tuple[int, int]) -> list[tuple[int, int]]:
    rows, cols = shape
    seeds = [(0, col) for col in range(cols)]
    if rows > 1:
        seeds.extend((rows - 1, col) for col in range(cols))
    seeds.extend((row, 0) for row in range(1, max(rows - 1, 1)))
    if cols > 1:
        seeds.extend((row, cols - 1) for row in range(1, max(rows - 1, 1)))
    return seeds


def _sample_points(samples, shape) -> list[tuple[int, int]]:
    rows, cols = shape
    result = []
    for sample in samples or ():
        try:
            if isinstance(sample, dict):
                x = float(sample.get("x"))
                y = float(sample.get("y"))
                normalized = str(sample.get("coordinate_space", "normalized")).lower() not in {"pixel", "pixels"}
            else:
                x, y = float(sample[0]), float(sample[1])
                normalized = 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
        except (TypeError, ValueError, IndexError):
            continue
        if normalized:
            col = int(round(x * max(cols - 1, 1)))
            row = int(round(y * max(rows - 1, 1)))
        else:
            col = int(round(x))
            row = int(round(y))
        if 0 <= row < rows and 0 <= col < cols:
            result.append((row, col))
    return result


def _region_mask(shape: tuple[int, int], edit: dict) -> np.ndarray:
    rows, cols = shape
    coordinate_space = str(edit.get("coordinate_space", "normalized")).lower()
    normalized = coordinate_space not in {"pixel", "pixels", "image_pixel"}
    edit_shape = str(edit.get("shape", "circle")).lower()
    if edit_shape in {"stroke", "brush", "line"}:
        converted = []
        for point in edit.get("points", ()):
            try:
                x, y = (point.get("x"), point.get("y")) if isinstance(point, dict) else point[:2]
                x, y = float(x), float(y)
            except (TypeError, ValueError, IndexError):
                continue
            if normalized:
                x *= max(cols - 1, 1)
                y *= max(rows - 1, 1)
            converted.append((x, y))
        if not converted:
            return np.zeros(shape, dtype=bool)
        image = Image.new("L", (cols, rows), 0)
        draw = ImageDraw.Draw(image)
        radius = float(edit.get("radius_normalized", edit.get("radius_px", 0.02)))
        if normalized and "radius_px" not in edit:
            radius *= min(rows, cols)
        width = max(1, int(round(radius * 2.0)))
        if len(converted) == 1:
            x, y = converted[0]
            draw.ellipse((x - width / 2.0, y - width / 2.0, x + width / 2.0, y + width / 2.0), fill=255)
        else:
            draw.line(converted, fill=255, width=width, joint="curve")
            cap = max(1, width // 2)
            for x, y in (converted[0], converted[-1]):
                draw.ellipse((x - cap, y - cap, x + cap, y + cap), fill=255)
        return np.asarray(image, dtype=np.uint8) > 0
    if edit_shape in {"polygon", "poly", "freeform", "free_form"}:
        converted = []
        for point in edit.get("points", edit.get("vertices", ())):
            try:
                x, y = (point.get("x"), point.get("y")) if isinstance(point, dict) else point[:2]
                x = float(x)
                y = float(y)
            except (TypeError, ValueError, IndexError):
                continue
            if normalized:
                x *= max(cols - 1, 1)
                y *= max(rows - 1, 1)
            converted.append((x, y))
        if len(converted) < 3:
            return np.zeros(shape, dtype=bool)
        image = Image.new("L", (cols, rows), 0)
        ImageDraw.Draw(image).polygon(converted, fill=255)
        return np.asarray(image, dtype=np.uint8) > 0

    try:
        x = float(edit.get("x", edit.get("center_x", 0.5)))
        y = float(edit.get("y", edit.get("center_y", 0.5)))
    except (TypeError, ValueError):
        return np.zeros(shape, dtype=bool)
    if normalized:
        x *= max(cols - 1, 1)
        y *= max(rows - 1, 1)
    yy, xx = np.ogrid[:rows, :cols]
    if edit_shape in {"rectangle", "rect", "box"}:
        width = float(edit.get("width_normalized", edit.get("width_px", 0.05)))
        height = float(edit.get("region_height_normalized", edit.get("height_normalized", edit.get("height_px", 0.05))))
        if normalized and "width_px" not in edit:
            width *= cols
        if normalized and "height_px" not in edit:
            height *= rows
        return (np.abs(xx - x) <= width / 2.0) & (np.abs(yy - y) <= height / 2.0)
    radius = float(edit.get("radius_normalized", edit.get("radius_px", 0.02)))
    if normalized and "radius_px" not in edit:
        radius *= min(rows, cols)
    return (xx - x) ** 2 + (yy - y) ** 2 <= radius**2


def _component_at(mask: np.ndarray, row: int, col: int, target: bool) -> np.ndarray:
    mask = np.asarray(mask, dtype=bool)
    if not (0 <= row < mask.shape[0] and 0 <= col < mask.shape[1]) or bool(mask[row, col]) != bool(target):
        return np.zeros_like(mask)
    return _connected_from_seeds(mask if target else ~mask, [(row, col)])


def apply_solid_mask_edits(mask: np.ndarray, edits=()) -> tuple[np.ndarray, dict]:
    """Apply ordered add/remove/fill/delete-component edits to a binary mask."""
    edit_list = list(edits or ())
    result = np.asarray(mask, dtype=bool).copy()
    changed = np.zeros_like(result)
    applied = []
    for index, raw in enumerate(edit_list):
        if not isinstance(raw, dict):
            continue
        edit = dict(raw)
        operation = str(edit.get("operation", "add")).lower()
        before = result.copy()
        if operation in {"fill", "fill_region", "delete_component", "remove_component"}:
            points = _sample_points([edit], result.shape)
            if not points:
                continue
            row, col = points[0]
            if operation in {"fill", "fill_region"}:
                region = _component_at(result, row, col, False)
                result[region] = True
            else:
                region = _component_at(result, row, col, True)
                result[region] = False
        else:
            region = _region_mask(result.shape, edit)
            if operation in {"remove", "subtract", "erase"}:
                result[region] = False
            elif operation == "toggle":
                result[region] = ~result[region]
            else:
                result[region] = True
        delta = before != result
        if delta.any():
            changed |= delta
            applied.append({"index": index, "operation": operation, "changed_pixel_count": int(delta.sum())})
    return result, {
        "requested_edit_count": len(edit_list),
        "applied_edit_count": len(applied),
        "changed_pixel_count": int(changed.sum()),
        "applied": applied,
    }


def draft_solid_mask(
    source: SourceImageData | str | Path | Image.Image | np.ndarray,
    *,
    mode: str = "auto_background",
    alpha_threshold: float = 1.0 / 255.0,
    background_samples=(),
    background_tolerance: float = 0.08,
    explicit_background: str | None = None,
    explicit_threshold: float = 0.9,
    edits=(),
) -> SolidMaskDraft:
    """Draft a binary material mask without assigning any height meaning."""
    data = source if isinstance(source, SourceImageData) else load_source_image(source)
    selected_mode = str(mode or "auto_background").strip().lower()
    if selected_mode not in SOLID_MODES:
        raise ValueError(f"unsupported solid mode: {selected_mode}")

    method = selected_mode
    informative_alpha = bool(data.alpha.size and float(data.alpha.min()) < float(data.alpha.max()))
    sample_points = _sample_points(background_samples, data.luminance.shape)
    tolerance = float(np.clip(background_tolerance, 0.0, np.sqrt(3.0)))
    alpha_threshold = float(np.clip(alpha_threshold, 0.0, 1.0))

    if selected_mode == "whole_plate":
        mask = np.ones(data.luminance.shape, dtype=bool)
        method = "whole_plate"
    else:
        if selected_mode == "auto_background" and informative_alpha:
            mask = data.alpha >= alpha_threshold
            method = "alpha"
        elif selected_mode == "auto_background" and sample_points:
            references = np.asarray([data.rgb[row, col] for row, col in sample_points], dtype=np.float32)
            distances = np.min(np.sqrt(np.mean((data.rgb[:, :, None, :] - references[None, None, :, :]) ** 2, axis=3)), axis=2)
            candidates = distances <= tolerance
            background = _connected_from_seeds(candidates, sample_points)
            mask = ~background
            method = "sampled_connected_background"
        elif explicit_background in {"bright", "dark"}:
            threshold = float(np.clip(explicit_threshold, 0.0, 1.0))
            candidates = data.luminance >= threshold if explicit_background == "bright" else data.luminance <= threshold
            background = _connected_from_seeds(candidates, _border_seeds(data.luminance.shape))
            mask = ~background
            method = f"explicit_{explicit_background}_connected_background"
        else:
            border = _border_values(data.rgb)
            reference = np.median(border, axis=0)
            border_distance = np.sqrt(np.mean((border - reference) ** 2, axis=1))
            adaptive = max(tolerance, float(np.percentile(border_distance, 95.0)) + 8.0 / 255.0)
            distances = np.sqrt(np.mean((data.rgb - reference) ** 2, axis=2))
            candidates = distances <= adaptive
            background = _connected_from_seeds(candidates, _border_seeds(data.luminance.shape))
            mask = ~background
            method = "border_connected_background"

    initial_count = int(mask.sum())
    mask, edit_report = apply_solid_mask_edits(mask, edits)
    report = {
        "artifact": "solid_mask",
        "semantic": {"true": "material exists", "false": "no material"},
        "requested_mode": selected_mode,
        "selected_method": method,
        "alpha_informative": informative_alpha,
        "background_sample_count": len(sample_points),
        "background_tolerance": tolerance,
        "initial_solid_pixel_count": initial_count,
        "final_solid_pixel_count": int(mask.sum()),
        "solid_fraction": float(mask.mean()) if mask.size else 0.0,
        "empty": not bool(mask.any()),
        "edits": edit_report,
        "height_information_used": False,
    }
    return SolidMaskDraft(mask=mask, report=report)


def percentile_normalize(
    luminance: np.ndarray,
    solid_mask: np.ndarray,
    *,
    low_percentile: float = 2.0,
    high_percentile: float = 98.0,
    black_point: float = 0.0,
    white_point: float = 1.0,
    midtone: float = 1.0,
    invert: bool = False,
) -> tuple[np.ndarray, dict]:
    """Normalize only finite solid pixels using robust percentiles."""
    values = np.asarray(luminance, dtype=np.float64)
    mask = np.asarray(solid_mask, dtype=bool)
    if values.shape != mask.shape or values.ndim != 2:
        raise ValueError("luminance and solid_mask must share one 2D shape")
    finite_mask = mask & np.isfinite(values)
    samples = values[finite_mask]
    if samples.size == 0:
        raise ValueError("solid region is empty or contains no finite luminance values")

    low = float(low_percentile)
    high = float(high_percentile)
    if not (0.0 <= low < high <= 100.0):
        raise ValueError("percentiles must satisfy 0 <= low < high <= 100")
    low_value = float(np.percentile(samples, low))
    high_value = float(np.percentile(samples, high))
    result = np.zeros(values.shape, dtype=np.float64)
    uniform = not np.isfinite(low_value + high_value) or high_value - low_value <= 1e-12
    if uniform:
        result[finite_mask] = 0.5
    else:
        result[finite_mask] = np.clip((values[finite_mask] - low_value) / (high_value - low_value), 0.0, 1.0)

    black = float(np.clip(black_point, 0.0, 1.0))
    white = float(np.clip(white_point, 0.0, 1.0))
    if white <= black:
        raise ValueError("white_point must be greater than black_point")
    gamma = float(midtone)
    if not np.isfinite(gamma) or gamma <= 0.0:
        raise ValueError("midtone must be a positive finite value")
    foreground = np.clip((result[finite_mask] - black) / (white - black), 0.0, 1.0)
    foreground = np.power(foreground, 1.0 / gamma)
    if invert:
        foreground = 1.0 - foreground
    result[finite_mask] = foreground
    result[~mask] = 0.0
    return result.astype(np.float32), {
        "low_percentile": low,
        "high_percentile": high,
        "low_value": low_value,
        "high_value": high_value,
        "sample_count": int(samples.size),
        "finite_sample_count": int(samples.size),
        "uniform_fallback": uniform,
        "black_point": black,
        "white_point": white,
        "midtone": gamma,
        "inverted": bool(invert),
        "outside_mask_fixed_to_zero": True,
    }


def _soft_line_influence(line_mask: np.ndarray, softness_px: float) -> np.ndarray:
    values = (np.asarray(line_mask, dtype=np.uint8) * 255)
    if float(softness_px) <= 0.0:
        return values.astype(np.float32) / 255.0
    image = Image.fromarray(values, mode="L").filter(ImageFilter.GaussianBlur(radius=float(softness_px)))
    return np.asarray(image, dtype=np.float32) / 255.0


def _split_height_edits(edits) -> tuple[list[dict], list[dict]]:
    region = []
    local = []
    for edit in edits or ():
        if not isinstance(edit, dict):
            continue
        stage = str(edit.get("stage", "local")).strip().lower()
        if stage in {"region", "region_fixed", "fixed_region", "region_fixed_height"}:
            region.append(dict(edit))
        else:
            local.append(dict(edit))
    return region, local


def draft_height_master(
    source: SourceImageData | str | Path | Image.Image | np.ndarray,
    solid_mask: np.ndarray,
    *,
    mode: str,
    low_percentile: float = 2.0,
    high_percentile: float = 98.0,
    black_point: float = 0.0,
    white_point: float = 1.0,
    midtone: float = 1.0,
    invert: bool = False,
    fixed_height: float = 1.0,
    line_threshold: float = 0.35,
    line_polarity: str = "dark",
    line_depth_mm: float = 0.2,
    relief_height_mm: float = 3.0,
    line_base_height: float | None = None,
    line_softness_px: float = 0.75,
    height_edits=(),
) -> HeightMasterDraft:
    """Create a user-selected height interpretation inside an approved mask."""
    data = source if isinstance(source, SourceImageData) else load_source_image(source)
    mask = np.asarray(solid_mask, dtype=bool)
    if mask.shape != data.luminance.shape:
        raise ValueError("solid_mask must match the source image size")
    if not mask.any():
        raise ValueError("solid_mask is empty")
    selected_mode = str(mode).strip().lower()
    if selected_mode not in HEIGHT_MODES:
        raise ValueError(f"unsupported height mode: {selected_mode}")

    polarity_invert = selected_mode == "dark_high"
    normalized, normalization_report = percentile_normalize(
        data.luminance,
        mask,
        low_percentile=low_percentile,
        high_percentile=high_percentile,
        black_point=black_point,
        white_point=white_point,
        midtone=midtone,
        invert=bool(invert) ^ polarity_invert,
    )
    line_mask = np.zeros(mask.shape, dtype=bool)
    line_report = {
        "enabled": False,
        "requested_depth_mm": 0.0,
        "applied_depth_mm": 0.0,
        "clipped_pixel_count": 0,
    }

    if selected_mode in {"bright_high", "dark_high"}:
        height = normalized
    elif selected_mode == "fixed":
        value = float(np.clip(fixed_height, 0.0, 1.0))
        height = np.where(mask, value, 0.0).astype(np.float32)
    else:
        relief = float(relief_height_mm)
        depth = float(line_depth_mm)
        if not np.isfinite(relief) or relief <= 0.0:
            raise ValueError("relief_height_mm must be positive for line modes")
        if not np.isfinite(depth) or depth < 0.0:
            raise ValueError("line_depth_mm must be a non-negative finite value")
        threshold = float(np.clip(line_threshold, 0.0, 1.0))
        polarity = str(line_polarity or "dark").strip().lower()
        if polarity not in {"dark", "light"}:
            raise ValueError("line_polarity must be dark or light")
        line_mask = (normalized <= threshold) if polarity == "dark" else (normalized >= threshold)
        line_mask &= mask
        influence = _soft_line_influence(line_mask, line_softness_px) * mask
        depth_normalized = depth / relief
        if line_base_height is None:
            base = 1.0 if selected_mode == "line_engrave" else 0.0
        else:
            base = float(np.clip(line_base_height, 0.0, 1.0))
        raw = base - depth_normalized * influence if selected_mode == "line_engrave" else base + depth_normalized * influence
        clipped = (raw < 0.0) | (raw > 1.0)
        height = np.where(mask, np.clip(raw, 0.0, 1.0), 0.0).astype(np.float32)
        applied_depth = min(depth, relief * (base if selected_mode == "line_engrave" else 1.0 - base))
        line_report = {
            "enabled": True,
            "mode": selected_mode,
            "polarity": polarity,
            "threshold": threshold,
            "base_height_normalized": base,
            "requested_depth_mm": depth,
            "applied_depth_mm": float(applied_depth),
            "depth_normalized": float(depth_normalized),
            "softness_px": float(max(line_softness_px, 0.0)),
            "line_pixel_count": int(line_mask.sum()),
            "clipped_pixel_count": int(np.count_nonzero(clipped & mask)),
        }

    region_edits, local_edits = _split_height_edits(height_edits)
    height, region_report = apply_manual_height_markers(height, mask, region_edits)
    height, local_report = apply_manual_height_markers(height, mask, local_edits)
    height = np.where(mask, np.clip(height, 0.0, 1.0), 0.0).astype(np.float32)
    report = {
        "artifact": "height_master",
        "meaning": {"0.0": "lowest solid surface", "1.0": "highest solid surface"},
        "requested_mode": selected_mode,
        "luminance_is_depth": False,
        "normalization": normalization_report,
        "line_relief": line_report,
        "region_fixed_height_edits": region_report,
        "local_manual_edits": local_report,
        "operation_order": list(HEIGHT_OPERATION_ORDER),
        "minimum": float(height[mask].min()),
        "maximum": float(height[mask].max()),
        "outside_mask_fixed_to_zero": bool(np.all(height[~mask] == 0.0)),
    }
    return HeightMasterDraft(height_master=height, line_mask=line_mask, report=report)


def _height_preview(height: np.ndarray, mask: np.ndarray) -> np.ndarray:
    values = np.where(mask, np.clip(height, 0.0, 1.0), 0.0)
    return np.round(values * 255.0).astype(np.uint8)


def _shaded_preview(height: np.ndarray, mask: np.ndarray) -> np.ndarray:
    values = np.asarray(height, dtype=np.float32)
    if min(values.shape) < 2:
        return _height_preview(values, mask)
    dy, dx = np.gradient(values)
    nx = -dx
    ny = -dy
    nz = np.ones_like(values) * 0.55
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= np.maximum(norm, 1e-8)
    ny /= np.maximum(norm, 1e-8)
    nz /= np.maximum(norm, 1e-8)
    light = np.asarray([-0.45, -0.55, 0.70], dtype=np.float32)
    light /= np.linalg.norm(light)
    shade = np.clip(nx * light[0] + ny * light[1] + nz * light[2], 0.0, 1.0)
    shade = np.where(mask, 0.2 + 0.8 * shade, 0.0)
    return np.round(shade * 255.0).astype(np.uint8)


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)


def export_workflow_artifacts(
    source: SourceImageData | str | Path | Image.Image | np.ndarray,
    solid_mask: np.ndarray,
    height_master: np.ndarray,
    output_dir: str | Path,
    *,
    solid_mask_confirmed: bool,
    height_master_confirmed: bool,
    solid_report: dict | None = None,
    height_report: dict | None = None,
    source_parameters: dict | None = None,
    solid_edits=(),
    height_edits=(),
    canvas_state: dict | None = None,
) -> WorkflowArtifacts:
    """Write the canonical source/mask/height/project artifact set atomically."""
    data = source if isinstance(source, SourceImageData) else load_source_image(source)
    mask = np.asarray(solid_mask, dtype=bool)
    height = np.asarray(height_master, dtype=np.float32)
    if mask.shape != data.luminance.shape or height.shape != mask.shape:
        raise ValueError("source, solid_mask and height_master must share one shape")
    if not np.isfinite(height).all():
        raise ValueError("height_master contains non-finite values")
    height = np.where(mask, np.clip(height, 0.0, 1.0), 0.0).astype(np.float32)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "source_aligned": output / "source_aligned.png",
        "solid_mask": output / "solid_mask.png",
        "height_master_16bit": output / "height_master_16bit.png",
        "height_master_32bit": output / "height_master_32bit.tiff",
        "height_master_preview": output / "height_master_preview.png",
        "mesh_preview": output / "mesh_preview.png",
        "project": output / "project.json",
        "build_report": output / "build_report.json",
    }

    Image.fromarray(data.rgba8, mode="RGBA").save(paths["source_aligned"])
    Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(paths["solid_mask"])
    Image.fromarray(np.round(height * 65535.0).astype(np.uint16)).save(paths["height_master_16bit"])
    Image.fromarray(height, mode="F").save(paths["height_master_32bit"])
    Image.fromarray(_height_preview(height, mask), mode="L").save(paths["height_master_preview"])
    Image.fromarray(_shaded_preview(height, mask), mode="L").save(paths["mesh_preview"])

    review_required = not (bool(solid_mask_confirmed) and bool(height_master_confirmed))
    file_hashes = {name: sha256_file(path) for name, path in paths.items() if name not in {"project", "build_report"}}
    project = {
        "file_version": 2,
        "editor_schema_version": 2,
        "workflow": "deterministic_grayscale_relief",
        "source_role": "reference_only_after_approval",
        "source_path": data.source_path,
        "source_mode": data.source_mode,
        "source_dtype": data.source_dtype,
        "files": {name: path.name for name, path in paths.items()},
        "file_hashes": file_hashes,
        "solid_mask_confirmed": bool(solid_mask_confirmed),
        "height_master_confirmed": bool(height_master_confirmed),
        "review_required": review_required,
        "source_parameters": dict(source_parameters or {}),
        "solid_mask_report": dict(solid_report or {}),
        "height_master_report": dict(height_report or {}),
        "solid_mask_edits": list(solid_edits or ()),
        "height_edits": list(height_edits or ()),
        "canvas_state": dict(canvas_state or {}),
        "height_operation_order": list(HEIGHT_OPERATION_ORDER),
        "mesh_input_policy": ["approved solid_mask", "approved height_master", "physical dimensions", "mesh sampling settings"],
        "mesh_forbidden_inputs": ["source image inference", "semantic classification", "background detection", "automatic line interpretation"],
    }
    _atomic_json(paths["project"], project)
    file_hashes["project"] = sha256_file(paths["project"])

    report = {
        "workflow": "deterministic_grayscale_relief",
        "stage": "approved_artifact_generation",
        "status": "review_required" if review_required else "approved_artifacts_ready",
        "review_required": review_required,
        "solid_mask_confirmed": bool(solid_mask_confirmed),
        "height_master_confirmed": bool(height_master_confirmed),
        "source_image_used_for_mesh": False,
        "luminance_is_depth": False,
        "real_photo_notice": "Brightness mapping is a draft, not recovered real geometry. Manual review and correction are required.",
        "shape": [int(mask.shape[0]), int(mask.shape[1])],
        "solid_pixel_count": int(mask.sum()),
        "height_range_inside_solid": [float(height[mask].min()) if mask.any() else 0.0, float(height[mask].max()) if mask.any() else 0.0],
        "files": {name: path.name for name, path in paths.items()},
        "file_hashes": file_hashes,
    }
    _atomic_json(paths["build_report"], report)
    report["file_hashes"]["build_report"] = sha256_file(paths["build_report"])
    return WorkflowArtifacts(paths={name: str(path) for name, path in paths.items()}, report=report, project=project)


def load_workflow_project(project_path: str | Path) -> dict:
    """Load and minimally validate a deterministic project manifest."""
    path = Path(project_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("workflow") != "deterministic_grayscale_relief":
        raise ValueError("not a deterministic grayscale relief project")
    for field in ("solid_mask_confirmed", "height_master_confirmed", "files"):
        if field not in payload:
            raise ValueError(f"project is missing {field}")
    return payload


def load_workflow_artifacts(project_path: str | Path, *, verify_hashes: bool = True) -> LoadedWorkflowArtifacts:
    """Load the canonical approved artifacts and verify their persisted hashes."""
    path = Path(project_path).resolve()
    project = load_workflow_project(path)
    files = project.get("files", {})
    required = ("source_aligned", "solid_mask", "height_master_16bit")
    missing = [name for name in required if not files.get(name)]
    if missing:
        raise ValueError(f"project is missing canonical files: {', '.join(missing)}")
    resolved = {name: (path.parent / str(files[name])).resolve() for name in required}
    for name, artifact_path in resolved.items():
        try:
            artifact_path.relative_to(path.parent.resolve())
        except ValueError as exc:
            raise ValueError(f"project artifact escapes its project directory: {name}") from exc
        if not artifact_path.is_file():
            raise FileNotFoundError(f"project artifact does not exist: {artifact_path}")

    if verify_hashes:
        hashes = project.get("file_hashes", {})
        for name, artifact_path in resolved.items():
            expected = hashes.get(name)
            if expected and sha256_file(artifact_path) != str(expected).lower():
                raise ValueError(f"project artifact hash mismatch: {name}")

    source = load_source_image(resolved["source_aligned"])
    with Image.open(resolved["solid_mask"]) as image:
        mask = np.asarray(image.convert("L"), dtype=np.uint8) >= 128
    with Image.open(resolved["height_master_16bit"]) as image:
        image_mode = str(image.mode)
        array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError("saved height master is not single-channel")
    if array.dtype == np.uint16 or image_mode.startswith("I;16"):
        height = array.astype(np.float32) / 65535.0
    elif np.issubdtype(array.dtype, np.integer) and int(array.max(initial=0)) <= 65535:
        height = array.astype(np.float32) / 65535.0
    else:
        raise ValueError("saved formal height master is not 16-bit")
    if source.luminance.shape != mask.shape or mask.shape != height.shape:
        raise ValueError("saved source, solid mask and height master are misaligned")
    if not np.isfinite(height).all():
        raise ValueError("saved height master contains non-finite values")
    height = np.where(mask, np.clip(height, 0.0, 1.0), 0.0).astype(np.float32)
    return LoadedWorkflowArtifacts(
        source=source,
        solid_mask=mask,
        height_master=height,
        project=project,
        project_path=str(path),
    )
