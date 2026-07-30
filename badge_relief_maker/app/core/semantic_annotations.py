"""Persistent semantic topology and height annotations."""

from collections import Counter

import numpy as np

from .components import connected_components
from .options import SEMANTIC_ROLES


SEMANTIC_HEIGHTS = {
    "base": 0.18,
    "low": 0.34,
    "mid": 0.52,
    "high": 0.72,
    "top": 0.90,
}


def _finite(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def normalize_semantic_annotation(annotation):
    """Return a safe normalized annotation or ``None``."""
    if not isinstance(annotation, dict):
        return None
    role = str(annotation.get("role", annotation.get("semantic_role", ""))).strip().lower()
    if role not in SEMANTIC_ROLES:
        return None
    tool = str(annotation.get("tool", "part")).strip().lower()
    if tool not in {"part", "brush"}:
        return None
    x = _finite(annotation.get("x"))
    y = _finite(annotation.get("y"))
    if x is None or y is None:
        return None
    coordinate_space = str(annotation.get("coordinate_space", "normalized")).strip().lower()
    radius = _finite(annotation.get("radius_px", annotation.get("radius_normalized", 0.03)))
    if radius is None or radius < 0.0:
        return None
    amount = _finite(annotation.get("amount", 0.12))
    return {
        "role": role,
        "tool": tool,
        "x": float(x),
        "y": float(y),
        "coordinate_space": coordinate_space,
        "radius": float(radius),
        "radius_is_normalized": "radius_px" not in annotation,
        "amount": float(np.clip(0.12 if amount is None else abs(amount), 0.0, 1.0)),
        "locked": bool(annotation.get("locked", True)),
        "annotation_id": str(annotation.get("annotation_id", "")),
    }


def transform_semantic_annotations(annotations, image_transform):
    """Map persisted source-space annotations into the final geometry grid."""
    rows, cols = image_transform.target_shape
    original_rows, original_cols = image_transform.original_shape
    transformed = []
    for raw in annotations or ():
        item = normalize_semantic_annotation(raw)
        if item is None:
            continue
        space = item["coordinate_space"]
        if space in {"final_normalized", "geometry_normalized", "target_normalized"}:
            x = item["x"] * max(cols - 1, 1)
            y = item["y"] * max(rows - 1, 1)
            radius = item["radius"] * min(rows, cols) if item["radius_is_normalized"] else item["radius"]
        else:
            normalized = space not in {"pixel", "pixels", "image_pixel"}
            x, y = image_transform.original_to_target_point(item["x"], item["y"], normalized=normalized)
            source_radius = item["radius"]
            if item["radius_is_normalized"]:
                source_radius *= min(original_rows, original_cols)
            radius = image_transform.original_radius_to_processed(source_radius)
        item.update({"x": float(x), "y": float(y), "radius": float(radius), "coordinate_space": "final"})
        transformed.append(item)
    return transformed


def _point(annotation, shape):
    rows, cols = shape
    space = annotation["coordinate_space"]
    if space in {"pixel", "pixels", "image_pixel", "final"}:
        x, y = annotation["x"], annotation["y"]
    else:
        x = annotation["x"] * max(cols - 1, 1)
        y = annotation["y"] * max(rows - 1, 1)
    return int(np.clip(round(y), 0, rows - 1)), int(np.clip(round(x), 0, cols - 1))


def _component_region(mask, row, col):
    target = bool(mask[row, col])
    for component in connected_components(mask, target=target):
        if (row, col) not in component.pixels:
            continue
        if not target and component.touches_border:
            return np.zeros(mask.shape, dtype=bool)
        region = np.zeros(mask.shape, dtype=bool)
        component_rows, component_cols = zip(*component.pixels)
        region[np.asarray(component_rows), np.asarray(component_cols)] = True
        return region
    return np.zeros(mask.shape, dtype=bool)


def _annotation_region(mask, annotation, lineart_labels=None):
    rows, cols = mask.shape
    row, col = _point(annotation, mask.shape)
    if annotation["tool"] == "part":
        labels = None if lineart_labels is None else np.asarray(lineart_labels, dtype=np.int32)
        if labels is not None and labels.shape == mask.shape:
            region_id = int(labels[row, col])
            if region_id > 0:
                return labels == region_id, region_id
            # A line-art analyzer deliberately rejected this point as too
            # small/noisy. Refuse a whole-footprint fallback: the brush tool
            # is the explicit way to correct such a detail.
            return np.zeros(mask.shape, dtype=bool), None
        return _component_region(mask, row, col), None
    yy, xx = np.ogrid[:rows, :cols]
    radius = annotation["radius"]
    if annotation["radius_is_normalized"] and annotation["coordinate_space"] != "final":
        radius *= min(rows, cols)
    return (xx - col) ** 2 + (yy - row) ** 2 <= radius**2, None


def apply_semantic_topology(mask, annotations, *, lineart_labels=None):
    """Apply void/fill decisions before crop and automatic height generation."""
    result = np.asarray(mask, dtype=bool).copy()
    applied = []
    for raw in annotations or ():
        item = normalize_semantic_annotation(raw)
        if item is None:
            continue
        region, _ = _annotation_region(result, item, lineart_labels=lineart_labels)
        if not region.any():
            continue
        before = result.copy()
        if item["role"] == "void":
            result[region] = False
        elif item["role"] in SEMANTIC_HEIGHTS:
            result[region] = True
        else:
            continue
        changed = int(np.count_nonzero(before != result))
        applied.append({"role": item["role"], "changed_pixel_count": changed, "locked": item["locked"]})
    return result, {
        "requested_annotation_count": len(tuple(annotations or ())),
        "applied_topology_count": len(applied),
        "changed_pixel_count": int(sum(item["changed_pixel_count"] for item in applied)),
    }


def apply_semantic_heights(heightmap, mask, annotations, *, lineart_labels=None, locked=None):
    """Apply fixed levels or relative adjustments and return an affected mask."""
    result = np.asarray(heightmap, dtype=float).copy()
    footprint = np.asarray(mask, dtype=bool)
    affected = np.zeros(footprint.shape, dtype=bool)
    applied = []
    roles = Counter()
    for item in annotations or ():
        if not isinstance(item, dict) or item.get("coordinate_space") != "final":
            continue
        if locked is not None and bool(item.get("locked", True)) != bool(locked):
            continue
        role = str(item.get("role", ""))
        if role == "void":
            continue
        region, region_id = _annotation_region(footprint, item, lineart_labels=lineart_labels)
        region &= footprint
        if not region.any():
            continue
        if role in SEMANTIC_HEIGHTS:
            result[region] = SEMANTIC_HEIGHTS[role]
        elif role == "raise":
            result[region] = np.clip(result[region] + float(item["amount"]), 0.0, 1.0)
        elif role == "recess":
            result[region] = np.clip(result[region] - float(item["amount"]), 0.0, 1.0)
        else:
            continue
        affected |= region
        roles[role] += 1
        applied.append(
            {
                "annotation_id": item.get("annotation_id", ""),
                "role": role,
                "region_id": region_id,
                "locked": bool(item.get("locked", True)),
                "affected_pixel_count": int(region.sum()),
            }
        )
    return result.astype(np.float32), affected, {
        "applied_annotation_count": len(applied),
        "affected_pixel_count": int(affected.sum()),
        "role_counts": dict(roles),
        "applied": applied,
    }
