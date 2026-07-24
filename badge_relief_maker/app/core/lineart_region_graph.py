"""Boundary-aware region controls for achromatic line artwork.

A single line drawing does not encode an unambiguous depth ordering. This module
therefore does not guess that every enclosed white island is raised. It segments
light regions separated by ink, reports unresolved regions, and applies explicit
region-level corrections selected by the user.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi


def _grayscale(rgba):
    values = np.asarray(rgba)
    if values.ndim != 3 or values.shape[2] != 4:
        raise ValueError("expected rgba image")
    rgb = values[:, :, :3].astype(np.float32) / 255.0
    return (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]).astype(np.float32)


def segment_lineart_regions(rgba, footprint, light_threshold=0.70):
    """Label light planar regions inside the current physical footprint.

    Ink acts only as a boundary separator. The labels are not depth levels and
    must never be interpreted as raised surfaces merely because they are enclosed.
    """
    gray = _grayscale(rgba)
    foreground = np.asarray(footprint, dtype=bool)
    if foreground.shape != gray.shape:
        raise ValueError("footprint and artwork must have the same shape")
    light = (gray >= float(light_threshold)) & foreground
    labels, count = ndi.label(light, structure=np.asarray([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8))
    return labels.astype(np.int32), int(count), gray


def analyze_lineart_regions(rgba, footprint, minimum_pixels=None):
    """Return a deterministic unresolved-region report for a line drawing."""
    foreground = np.asarray(footprint, dtype=bool)
    labels, count, _ = segment_lineart_regions(rgba, foreground)
    minimum = int(minimum_pixels or max(12, round(max(int(foreground.sum()), 1) * 0.00015)))
    regions = []
    for label_id in range(1, count + 1):
        region = labels == label_id
        area = int(region.sum())
        if area < minimum:
            continue
        ys, xs = np.nonzero(region)
        if not len(xs):
            continue
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        regions.append(
            {
                "region_id": int(label_id),
                "pixel_count": area,
                "centroid_normalized": [
                    float((xs.mean() + 0.5) / max(labels.shape[1], 1)),
                    float((ys.mean() + 0.5) / max(labels.shape[0], 1)),
                ],
                "bbox_normalized": [
                    float(x0 / max(labels.shape[1], 1)),
                    float(y0 / max(labels.shape[0], 1)),
                    float(x1 / max(labels.shape[1], 1)),
                    float(y1 / max(labels.shape[0], 1)),
                ],
                "status": "unresolved",
            }
        )
    regions.sort(key=lambda item: (-item["pixel_count"], item["region_id"]))
    return labels, {
        "segmented_region_count": int(count),
        "reported_region_count": len(regions),
        "minimum_reported_pixels": minimum,
        "unresolved_region_count": len(regions),
        "requires_region_confirmation": bool(regions),
        "default_policy": "neutral; never auto-raise an enclosed light region",
        "regions": regions,
    }


def _normalized_point(override, shape):
    rows, cols = shape
    x = float(override.get("x", 0.5))
    y = float(override.get("y", 0.5))
    space = str(override.get("coordinate_space", "final_normalized")).lower()
    if space in {"pixel", "final_pixel"}:
        px = int(np.clip(round(x), 0, max(cols - 1, 0)))
        py = int(np.clip(round(y), 0, max(rows - 1, 0)))
    else:
        px = int(np.clip(round(x * max(cols - 1, 0)), 0, max(cols - 1, 0)))
        py = int(np.clip(round(y * max(rows - 1, 0)), 0, max(rows - 1, 0)))
    return py, px


def _boundary_reference(values, foreground, region):
    ring = ndi.binary_dilation(region, iterations=2) & foreground & ~region
    sample = values[ring]
    if sample.size:
        return float(np.median(sample))
    sample = values[foreground & ~region]
    return float(np.median(sample)) if sample.size else 0.25


def apply_lineart_region_overrides(rgba, footprint, heightmap, overrides=()):
    """Apply click-selected region roles to the footprint and height field.

    Supported roles:
    - ``background`` / ``hole``: remove the region from the physical footprint;
    - ``surface``: keep it on the same level as its surrounding surface;
    - ``raise``: add a smooth regional dome above the surrounding surface;
    - ``recess`` / ``shadow``: place it below the surrounding surface.
    """
    mask = np.asarray(footprint, dtype=bool).copy()
    height = np.asarray(heightmap, dtype=np.float32).copy()
    labels, _, _ = segment_lineart_regions(rgba, mask)
    applied = []
    skipped = []

    for index, raw in enumerate(overrides or ()):
        if not isinstance(raw, dict):
            skipped.append({"index": index, "reason": "override is not an object"})
            continue
        py, px = _normalized_point(raw, labels.shape)
        label_id = int(labels[py, px])
        if label_id <= 0:
            skipped.append({"index": index, "reason": "point is not inside a light line-art region"})
            continue
        region = labels == label_id
        role = str(raw.get("role", raw.get("operation", "surface"))).strip().lower()
        reference = _boundary_reference(height, mask, region)
        amount = float(np.clip(raw.get("amount", raw.get("value", 0.18)), 0.0, 1.0))

        if role in {"background", "hole", "void"}:
            mask[region] = False
            height[region] = 0.0
        elif role in {"surface", "same", "neutral"}:
            height[region] = reference
        elif role in {"raise", "raised", "foreground"}:
            distance = ndi.distance_transform_edt(region)
            maximum = float(distance.max())
            dome = distance / maximum if maximum > 0.0 else np.ones(region.shape, dtype=np.float32)
            height[region] = np.clip(reference + amount * np.power(dome[region], 0.55), 0.0, 1.0)
        elif role in {"recess", "recessed", "shadow", "engrave"}:
            height[region] = np.clip(reference - amount, 0.0, 1.0)
        else:
            skipped.append({"index": index, "reason": f"unsupported role: {role}"})
            continue
        applied.append({"index": index, "region_id": label_id, "role": role, "pixel_count": int(region.sum())})

    height = np.where(mask, np.clip(height, 0.0, 1.0), 0.0).astype(np.float32)
    return mask, height, {
        "requested_override_count": len(tuple(overrides or ())),
        "applied_override_count": len(applied),
        "applied": applied,
        "skipped": skipped,
    }
