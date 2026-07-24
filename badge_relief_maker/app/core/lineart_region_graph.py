"""Boundary-aware region controls for achromatic line artwork.

A single line drawing does not encode an unambiguous depth ordering.  This module
therefore does not guess that every enclosed white island is raised.  It segments
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

    Ink acts only as a boundary separator.  The labels are not depth levels and
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
    """Return a deterministic unresolved-region report for a line drawing.

    ``display_id`` is assigned by descending region area and is included directly
    in the report so screenshots and user feedback can reference a stable visible
    number for the current processing grid. The underlying connected-component id
    is retained as ``region_id``.
    """
    foreground = np.asarray(footprint, dtype=bool)
    labels, count, _ = segment_lineart_regions(rgba, foreground)
    minimum = int(minimum_pixels or max(48, round(max(int(foreground.sum()), 1) * 0.0012)))
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
    for display_id, item in enumerate(regions, start=1):
        item["display_id"] = int(display_id)
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
    """Estimate the carrier surface without sampling the dark boundary groove."""
    near = ndi.binary_dilation(region, iterations=3)
    far = ndi.binary_dilation(region, iterations=8)
    ring = far & ~near & foreground & ~region
    sample = np.asarray(values, dtype=np.float32)[ring]
    if sample.size:
        return float(np.percentile(sample, 60.0))
    sample = np.asarray(values, dtype=np.float32)[foreground & ~region]
    return float(np.median(sample)) if sample.size else 0.25


def _component_profile(region, exponent=0.62):
    labels, count = ndi.label(region)
    result = np.zeros(region.shape, dtype=np.float32)
    for label_id in range(1, int(count) + 1):
        component = labels == label_id
        distance = ndi.distance_transform_edt(component)
        maximum = float(distance.max())
        if maximum <= 0.0:
            result[component] = 1.0
        else:
            result[component] = np.power(np.clip(distance[component] / maximum, 0.0, 1.0), float(exponent))
    return result


def _region_from_override(raw, labels, region_report):
    if "region_id" in raw:
        try:
            label_id = int(raw.get("region_id"))
        except (TypeError, ValueError):
            label_id = 0
    elif "display_id" in raw:
        try:
            display_id = int(raw.get("display_id"))
        except (TypeError, ValueError):
            display_id = 0
        match = next((item for item in region_report.get("regions", []) if int(item.get("display_id", -1)) == display_id), None)
        label_id = int(match.get("region_id", 0)) if match is not None else 0
    else:
        py, px = _normalized_point(raw, labels.shape)
        label_id = int(labels[py, px])
    return label_id, labels == label_id if label_id > 0 else np.zeros(labels.shape, dtype=bool)


def apply_lineart_region_overrides(
    rgba,
    footprint,
    heightmap,
    overrides=(),
    *,
    region_labels=None,
    region_report=None,
):
    """Apply explicit region roles to the footprint and height field.

    Overrides may select a region by a click point, raw ``region_id`` or visible
    ``display_id``. ``raise``/``component`` can optionally include nearby dark ink
    with ``grow_into_ink_px`` so a white ribbon panel and its outlined/hatched edge
    become one physical component rather than a partial floating patch.
    """
    mask = np.asarray(footprint, dtype=bool).copy()
    height = np.asarray(heightmap, dtype=np.float32).copy()
    if region_labels is None or region_report is None:
        labels, region_report = analyze_lineart_regions(rgba, mask)
    else:
        labels = np.asarray(region_labels, dtype=np.int32)
        if labels.shape != mask.shape:
            raise ValueError("region labels and footprint must have the same shape")
        region_report = dict(region_report)
        region_report["regions"] = [dict(item) for item in region_report.get("regions", [])]
    gray = _grayscale(rgba)
    applied = []
    skipped = []
    override_list = tuple(overrides or ())

    for index, raw in enumerate(override_list):
        if not isinstance(raw, dict):
            skipped.append({"index": index, "reason": "override is not an object"})
            continue
        label_id, region = _region_from_override(raw, labels, region_report)
        if label_id <= 0 or not region.any():
            skipped.append({"index": index, "reason": "region could not be resolved"})
            continue
        role = str(raw.get("role", raw.get("operation", "surface"))).strip().lower()
        display_match = next((item for item in region_report["regions"] if int(item["region_id"]) == label_id), None)
        display_id = int(display_match["display_id"]) if display_match is not None else None

        grow_px = max(float(raw.get("grow_into_ink_px", raw.get("include_boundary_px", 0.0)) or 0.0), 0.0)
        working_region = region
        if grow_px > 0.0 and role in {"surface", "same", "neutral", "raise", "raised", "foreground", "component"}:
            iterations = max(int(round(grow_px)), 1)
            nearby = ndi.binary_dilation(region, iterations=iterations) & mask
            ink_threshold = float(raw.get("ink_threshold", 0.76))
            working_region = region | (nearby & (gray < ink_threshold))
            if bool(raw.get("close_component", True)):
                working_region = ndi.binary_closing(working_region, iterations=max(1, iterations // 3)) & mask

        reference = _boundary_reference(height, mask, working_region)
        amount = float(np.clip(raw.get("amount", raw.get("value", 0.18)), 0.0, 1.0))

        if role in {"background", "hole", "void"}:
            mask[region] = False
            height[region] = 0.0
        elif role in {"surface", "same", "neutral"}:
            detail_mix = float(np.clip(raw.get("detail_mix", 0.12), 0.0, 1.0))
            local = height[working_region]
            detail = local - float(np.median(local)) if local.size else 0.0
            height[working_region] = np.clip(reference + detail_mix * detail, 0.0, 1.0)
        elif role in {"raise", "raised", "foreground", "component"}:
            exponent = max(float(raw.get("profile_exponent", 0.62)), 0.05)
            profile = _component_profile(working_region, exponent=exponent)
            peak = float(np.clip(raw.get("peak_height", reference + amount), 0.0, 1.0))
            target = reference + (peak - reference) * profile
            detail_mix = float(np.clip(raw.get("detail_mix", 0.10), 0.0, 1.0))
            if detail_mix > 0.0:
                smooth = ndi.gaussian_filter(height, sigma=max(float(raw.get("detail_sigma", 1.8)), 0.1))
                target = np.clip(target + (height - smooth) * detail_mix, 0.0, 1.0)
            height[working_region] = target[working_region]
        elif role in {"recess", "recessed", "shadow", "engrave"}:
            profile = _component_profile(region, exponent=max(float(raw.get("profile_exponent", 0.85)), 0.05))
            height[region] = np.clip(reference - amount * profile[region], 0.0, 1.0)
        else:
            skipped.append({"index": index, "reason": f"unsupported role: {role}"})
            continue
        applied.append(
            {
                "index": index,
                "region_id": label_id,
                "display_id": display_id,
                "role": role,
                "pixel_count": int(region.sum()),
                "effective_pixel_count": int(working_region.sum()),
            }
        )

    height = np.where(mask, np.clip(height, 0.0, 1.0), 0.0).astype(np.float32)
    return mask, height, {
        "requested_override_count": len(override_list),
        "applied_override_count": len(applied),
        "applied": applied,
        "skipped": skipped,
    }


def save_lineart_region_preview(rgba, labels, region_report, override_report, path):
    """Save a colour-coded map of major line-art regions and their current roles."""
    from pathlib import Path
    from PIL import Image, ImageDraw

    source = np.asarray(rgba, dtype=np.uint8)
    label_grid = np.asarray(labels, dtype=np.int32)
    if source.shape[:2] != label_grid.shape:
        raise ValueError("region labels and artwork must have the same shape")
    applied_roles = {
        int(item.get("region_id", -1)): str(item.get("role", "surface"))
        for item in (override_report or {}).get("applied", [])
        if isinstance(item, dict)
    }
    palette = {
        "unresolved": np.asarray([255, 196, 64], dtype=np.float32),
        "background": np.asarray([55, 150, 255], dtype=np.float32),
        "hole": np.asarray([55, 150, 255], dtype=np.float32),
        "surface": np.asarray([90, 210, 145], dtype=np.float32),
        "raise": np.asarray([255, 92, 76], dtype=np.float32),
        "raised": np.asarray([255, 92, 76], dtype=np.float32),
        "foreground": np.asarray([255, 92, 76], dtype=np.float32),
        "component": np.asarray([255, 92, 76], dtype=np.float32),
        "recess": np.asarray([160, 105, 235], dtype=np.float32),
    }
    output = source[:, :, :3].astype(np.float32) * 0.62 + 255.0 * 0.38
    regions = list((region_report or {}).get("regions", []))
    for fallback_display_id, item in enumerate(regions, start=1):
        display_id = int(item.get("display_id", fallback_display_id))
        region_id = int(item.get("region_id", -1))
        role = applied_roles.get(region_id, "unresolved")
        region = label_grid == region_id
        colour = palette.get(role, palette["unresolved"])
        output[region] = output[region] * 0.45 + colour * 0.55
        item["display_id"] = int(display_id)
        item["role"] = role

    image = Image.fromarray(np.clip(output, 0, 255).astype(np.uint8), mode="RGB")
    draw = ImageDraw.Draw(image)
    for item in regions:
        cx, cy = item.get("centroid_normalized", [0.5, 0.5])
        x = int(round(float(cx) * max(image.width - 1, 1)))
        y = int(round(float(cy) * max(image.height - 1, 1)))
        text = str(item.get("display_id", "?"))
        box = draw.textbbox((x, y), text, anchor="mm")
        draw.rectangle((box[0] - 1, box[1] - 1, box[2] + 1, box[3] + 1), fill=(245, 245, 245))
        draw.text((x, y), text, fill=(20, 20, 20), anchor="mm")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return str(path)
