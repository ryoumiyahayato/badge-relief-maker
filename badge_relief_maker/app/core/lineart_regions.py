"""Deterministic line-art regions used for guided semantic review."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi


ROLE_COLOURS = {
    "void": (54, 124, 245),
    "base": (55, 190, 180),
    "low": (68, 205, 132),
    "mid": (244, 204, 72),
    "high": (247, 142, 55),
    "top": (238, 71, 65),
    "raise": (245, 77, 94),
    "recess": (147, 91, 220),
    "unresolved": (250, 218, 75),
}


def grayscale(rgba):
    """Return perceptual grayscale in the normalized 0..1 range."""
    values = np.asarray(rgba, dtype=np.uint8)
    if values.ndim != 3 or values.shape[2] != 4:
        raise ValueError("expected an RGBA image")
    rgb = values[:, :, :3].astype(np.float32) / 255.0
    return (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]).astype(np.float32)


def analyze_lineart_regions(rgba, footprint, minimum_pixels=None, light_threshold=0.70):
    """Label both light cells and dark artwork without assigning either a height."""
    foreground = np.asarray(footprint, dtype=bool)
    gray = grayscale(rgba)
    if foreground.shape != gray.shape:
        raise ValueError("footprint and artwork must have the same shape")
    structure = np.asarray([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
    enclosed_void = ndi.binary_fill_holes(foreground) & ~foreground
    tone_masks = (
        ("light", "solid", (gray >= float(light_threshold)) & foreground),
        ("dark", "solid", (gray < float(light_threshold)) & foreground),
        ("light", "enclosed_void", (gray >= float(light_threshold)) & enclosed_void),
        ("dark", "enclosed_void", (gray < float(light_threshold)) & enclosed_void),
    )
    labels = np.zeros(foreground.shape, dtype=np.int32)
    minimum = int(minimum_pixels or max(24, round(max(int(foreground.sum()), 1) * 0.0008)))
    regions = []
    next_region_id = 1
    for tone_class, occupancy_class, tone_mask in tone_masks:
        tone_labels, count = ndi.label(tone_mask, structure=structure)
        for local_id in range(1, int(count) + 1):
            region = tone_labels == local_id
            pixel_count = int(region.sum())
            if pixel_count < minimum:
                continue
            rows, cols = np.nonzero(region)
            if not len(cols):
                continue
            labels[region] = next_region_id
            regions.append(
                {
                    "region_id": int(next_region_id),
                    "tone_class": tone_class,
                    "occupancy_class": occupancy_class,
                    "pixel_count": pixel_count,
                    "centroid_normalized": [
                        float((cols.mean() + 0.5) / max(labels.shape[1], 1)),
                        float((rows.mean() + 0.5) / max(labels.shape[0], 1)),
                    ],
                    "bbox_normalized": [
                        float(cols.min() / max(labels.shape[1], 1)),
                        float(rows.min() / max(labels.shape[0], 1)),
                        float((cols.max() + 1) / max(labels.shape[1], 1)),
                        float((rows.max() + 1) / max(labels.shape[0], 1)),
                    ],
                    "status": "unresolved",
                }
            )
            next_region_id += 1
    regions.sort(key=lambda item: (-item["pixel_count"], item["region_id"]))
    for display_id, item in enumerate(regions, start=1):
        item["display_id"] = int(display_id)
    return labels.astype(np.int32), {
        "regions": regions,
        "region_count": len(regions),
        "unresolved_region_count": len(regions),
        "interpretation": "light cells and dark artwork components; tone class has no automatic depth meaning",
    }


def save_semantic_region_preview(rgba, mask, labels, region_report, applied_annotations, path):
    """Save a numbered semantic map with resolved and unresolved colours."""
    source = np.asarray(rgba, dtype=np.uint8)
    footprint = np.asarray(mask, dtype=bool)
    region_labels = np.asarray(labels, dtype=np.int32)
    if source.shape[:2] != footprint.shape or region_labels.shape != footprint.shape:
        raise ValueError("semantic preview inputs must share one image shape")
    applied_by_region = {
        int(item["region_id"]): str(item["role"])
        for item in applied_annotations
        if item.get("region_id") is not None
    }
    output = source[:, :, :3].astype(np.float32) * 0.35
    output[~footprint] *= 0.30
    for item in region_report.get("regions", []):
        region_id = int(item["region_id"])
        role = applied_by_region.get(region_id, "unresolved")
        colour = np.asarray(ROLE_COLOURS.get(role, ROLE_COLOURS["unresolved"]), dtype=np.float32)
        region = region_labels == region_id
        output[region] = output[region] * 0.30 + colour * 0.70
        item["status"] = role

    image = Image.fromarray(np.clip(output, 0, 255).astype(np.uint8), mode="RGB")
    draw = ImageDraw.Draw(image)
    for item in region_report.get("regions", []):
        x, y = item["centroid_normalized"]
        point = (int(x * image.width), int(y * image.height))
        label = str(item["display_id"])
        box = draw.textbbox(point, label, anchor="mm")
        draw.ellipse((box[0] - 5, box[1] - 3, box[2] + 5, box[3] + 3), fill=(20, 23, 28))
        draw.text(point, label, fill=(255, 255, 255), anchor="mm")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return str(target)


def save_focused_region_preview(base_preview_path, region, output_path):
    """Highlight one region selected by the guided-review iterator."""
    image = Image.open(base_preview_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = region.get("bbox_normalized", [0.0, 0.0, 1.0, 1.0])
    bounds = (
        int(round(float(x0) * max(image.width - 1, 1))),
        int(round(float(y0) * max(image.height - 1, 1))),
        int(round(float(x1) * max(image.width - 1, 1))),
        int(round(float(y1) * max(image.height - 1, 1))),
    )
    for offset in range(max(2, image.width // 240)):
        draw.rectangle(
            (bounds[0] - offset, bounds[1] - offset, bounds[2] + offset, bounds[3] + offset),
            outline=(255, 72, 64),
        )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return str(target)
