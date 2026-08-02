"""Pure, deterministic operations used by the canvas-first editor.

The GUI deliberately stores only normalized coordinates.  This module keeps the
math independent from Qt so strokes can be tested, previewed and replayed at a
different raster size without changing their meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw


def clamp_normalized_point(point: Sequence[float]) -> tuple[float, float] | None:
    """Return a finite point in the normalized image rectangle, or ``None``."""
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))


def normalize_points(points: Iterable[Sequence[float]]) -> list[list[float]]:
    """Normalize a point sequence and drop invalid/outside points deterministically."""
    result = []
    for point in points or ():
        normalized = clamp_normalized_point(point)
        if normalized is not None:
            result.append([normalized[0], normalized[1]])
    return result


def interpolate_points(
    points: Iterable[Sequence[float]],
    maximum_spacing: float,
) -> list[list[float]]:
    """Insert linear points so no adjacent samples exceed ``maximum_spacing``.

    The endpoints are preserved and the number of inserted samples is derived
    only from the distance and spacing, making fast mouse motion reproducible.
    """
    source = normalize_points(points)
    if len(source) < 2:
        return source
    spacing = max(float(maximum_spacing), 1e-9)
    result = [source[0]]
    for start, end in zip(source, source[1:]):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.hypot(dx, dy)
        steps = max(1, int(math.ceil(distance / spacing)))
        for index in range(1, steps + 1):
            fraction = index / steps
            result.append([start[0] + dx * fraction, start[1] + dy * fraction])
    return result


def normalized_edit_record(
    operation: str,
    points: Iterable[Sequence[float]],
    radius_normalized: float,
    *,
    hardness: float = 0.8,
    **extra,
) -> dict:
    """Build the canonical persisted stroke representation."""
    radius = float(np.clip(float(radius_normalized), 1e-6, 1.0))
    samples = interpolate_points(points, radius * 0.25)
    record = {
        "operation": str(operation),
        "shape": "stroke",
        "points": samples,
        "coordinate_space": "normalized",
        "radius_normalized": radius,
    }
    if extra:
        record.update(extra)
    if "hardness" not in record:
        record["hardness"] = float(np.clip(float(hardness), 0.0, 1.0))
    return record


def stroke_roi(shape: tuple[int, int], points: Iterable[Sequence[float]], radius_normalized: float, margin: int = 1):
    """Return a clipped ``(row0, row1, col0, col1)`` ROI for a normalized stroke."""
    rows, cols = int(shape[0]), int(shape[1])
    samples = normalize_points(points)
    if not samples:
        return 0, 0, 0, 0
    radius = max(float(radius_normalized), 0.0) * min(rows, cols)
    col_values = [point[0] * max(cols - 1, 1) for point in samples]
    row_values = [point[1] * max(rows - 1, 1) for point in samples]
    col0 = max(0, int(math.floor(min(col_values) - radius)) - int(margin))
    col1 = min(cols, int(math.ceil(max(col_values) + radius)) + 1 + int(margin))
    row0 = max(0, int(math.floor(min(row_values) - radius)) - int(margin))
    row1 = min(rows, int(math.ceil(max(row_values) + radius)) + 1 + int(margin))
    return row0, row1, col0, col1


def _stroke_alpha(shape: tuple[int, int], points, radius_normalized: float, hardness: float = 1.0) -> np.ndarray:
    rows, cols = shape
    image = Image.new("L", (cols, rows), 0)
    draw = ImageDraw.Draw(image)
    samples = normalize_points(points)
    if not samples:
        return np.zeros(shape, dtype=np.float32)
    converted = [(round(x * max(cols - 1, 1)), round(y * max(rows - 1, 1))) for x, y in samples]
    width = max(1, int(round(float(radius_normalized) * 2.0 * min(rows, cols))))
    if len(converted) == 1:
        x, y = converted[0]
        draw.ellipse((x - width // 2, y - width // 2, x + width // 2, y + width // 2), fill=255)
    else:
        draw.line(converted, fill=255, width=width, joint="curve")
        radius = max(1, width // 2)
        for x, y in (converted[0], converted[-1]):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    alpha = np.asarray(image, dtype=np.float32) / 255.0
    hardness = float(np.clip(hardness, 0.0, 1.0))
    if hardness < 1.0:
        alpha = np.power(alpha, max(0.05, hardness))
    return alpha


def rasterize_solid_stroke(mask: np.ndarray, record: dict, *, roi=None) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Apply one add/remove stroke and return the changed mask plus its ROI."""
    result = np.asarray(mask, dtype=bool).copy()
    if str(record.get("shape", "")).lower() != "stroke":
        return result, (0, result.shape[0], 0, result.shape[1])
    points = record.get("points", ())
    radius = float(record.get("radius_normalized", 0.02))
    resolved_roi = roi or stroke_roi(result.shape, points, radius)
    row0, row1, col0, col1 = resolved_roi
    if row1 <= row0 or col1 <= col0:
        return result, resolved_roi
    # Rasterize in the full image coordinate system, then slice the result.
    # This avoids clipping normalized points at the ROI boundary and keeps the
    # exact same pixels as a full-resolution replay.
    alpha = _stroke_alpha(result.shape, points, radius)[row0:row1, col0:col1]
    selected = alpha >= 0.5
    operation = str(record.get("operation", "add")).lower()
    if operation in {"remove", "subtract", "erase"}:
        result[row0:row1, col0:col1][selected] = False
    else:
        result[row0:row1, col0:col1][selected] = True
    return result, resolved_roi


def apply_canvas_solid_edits(mask: np.ndarray, edits: Iterable[dict] = ()) -> np.ndarray:
    """Replay stroke records while delegating legacy shapes to the core helper."""
    from .deterministic_workflow import apply_solid_mask_edits

    result = np.asarray(mask, dtype=bool).copy()
    legacy = []
    for edit in edits or ():
        if isinstance(edit, dict) and str(edit.get("shape", "")).lower() == "stroke":
            result, _ = rasterize_solid_stroke(result, edit)
        else:
            legacy.append(edit)
            if legacy:
                result, _ = apply_solid_mask_edits(result, [legacy[-1]])
    return result


def _masked_mean(values: np.ndarray, mask: np.ndarray, radius: int = 1) -> np.ndarray:
    """Small deterministic masked box filter used by the smooth brush."""
    values = np.asarray(values, dtype=np.float32)
    mask = np.asarray(mask, dtype=bool)
    size = max(1, int(radius)) * 2 + 1
    padded_values = np.pad(values, size // 2, mode="edge")
    padded_mask = np.pad(mask.astype(np.float32), size // 2, mode="constant")
    total = np.zeros_like(values, dtype=np.float32)
    weight = np.zeros_like(values, dtype=np.float32)
    rows, cols = values.shape
    for row in range(size):
        for col in range(size):
            valid = padded_mask[row : row + rows, col : col + cols]
            total += padded_values[row : row + rows, col : col + cols] * valid
            weight += valid
    return np.divide(total, weight, out=values.copy(), where=weight > 0.0)


def rasterize_height_stroke(height: np.ndarray, mask: np.ndarray, record: dict, *, roi=None) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Apply one height stroke, updating only the stroke ROI and its edge margin."""
    result = np.asarray(height, dtype=np.float32).copy()
    solid = np.asarray(mask, dtype=bool)
    if result.shape != solid.shape:
        raise ValueError("height and mask must have the same shape")
    resolved_roi = roi or stroke_roi(result.shape, record.get("points", ()), record.get("radius_normalized", 0.02), margin=2)
    row0, row1, col0, col1 = resolved_roi
    if row1 <= row0 or col1 <= col0:
        return result, resolved_roi
    alpha = _stroke_alpha(
        result.shape,
        record.get("points", ()),
        float(record.get("radius_normalized", 0.02)),
        float(record.get("hardness", 0.8)),
    )[row0:row1, col0:col1]
    local = result[row0:row1, col0:col1].copy()
    local_mask = solid[row0:row1, col0:col1]
    operation = str(record.get("operation", "set")).lower()
    if operation == "smooth":
        smoothed = _masked_mean(result, solid, radius=max(1, round(float(record.get("radius_normalized", 0.02)) * min(result.shape) / 3.0)))
        target = smoothed[row0:row1, col0:col1]
        amount = float(np.clip(record.get("amount", record.get("value", 0.25)), 0.0, 1.0))
        local = local * (1.0 - alpha * amount) + target * (alpha * amount)
    elif operation == "add":
        local += alpha * float(np.clip(record.get("amount", record.get("value", 0.1)), 0.0, 1.0))
    elif operation in {"subtract", "lower", "decrease"}:
        local -= alpha * float(np.clip(record.get("amount", record.get("value", 0.1)), 0.0, 1.0))
    else:
        value = float(np.clip(record.get("value", record.get("height", 0.5)), 0.0, 1.0))
        local = local * (1.0 - alpha) + value * alpha
    local[~local_mask] = 0.0
    result[row0:row1, col0:col1] = np.clip(local, 0.0, 1.0)
    result[~solid] = 0.0
    return result.astype(np.float32), resolved_roi


def replay_height_edits(height: np.ndarray, mask: np.ndarray, edits: Iterable[dict] = ()) -> np.ndarray:
    """Replay all new stroke records and legacy marker records in order."""
    from .height_markers import apply_manual_height_markers

    result = np.asarray(height, dtype=np.float32).copy()
    legacy = []
    for edit in edits or ():
        if isinstance(edit, dict) and str(edit.get("shape", "")).lower() == "stroke":
            result, _ = rasterize_height_stroke(result, mask, edit)
        else:
            legacy.append(edit)
            result, _ = apply_manual_height_markers(result, mask, [legacy[-1]])
    return np.where(mask, np.clip(result, 0.0, 1.0), 0.0).astype(np.float32)


def replay_edits(base_mask: np.ndarray, base_height: np.ndarray | None, mask_edits=(), height_edits=()):
    """Replay both edit streams and return ``(mask, height)``."""
    mask = apply_canvas_solid_edits(base_mask, mask_edits)
    height = None if base_height is None else replay_height_edits(base_height, mask, height_edits)
    return mask, height


@dataclass(frozen=True)
class StrokeROI:
    row0: int
    row1: int
    col0: int
    col1: int

    @property
    def empty(self) -> bool:
        return self.row1 <= self.row0 or self.col1 <= self.col0
