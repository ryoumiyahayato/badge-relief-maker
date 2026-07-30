"""Deterministic uncertainty maps for manual review, not classifier scores."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from .lineart_regions import grayscale


def _robust_normalize(values, percentile=95.0):
    array = np.asarray(values, dtype=np.float32)
    finite = array[np.isfinite(array)]
    if not finite.size:
        return np.zeros(array.shape, dtype=np.float32)
    scale = float(np.percentile(finite, float(percentile)))
    return np.zeros(array.shape, dtype=np.float32) if scale <= 1e-8 else np.clip(array / scale, 0.0, 1.0)


def build_uncertainty_map(rgba, mask, *, lineart_labels=None, lineart_report=None, applied_annotations=()):
    """Combine weak boundaries, local noise, isolated specks and unresolved regions."""
    source = np.asarray(rgba, dtype=np.uint8)
    footprint = np.asarray(mask, dtype=bool)
    if source.shape[:2] != footprint.shape:
        raise ValueError("artwork and mask must have the same shape")
    gray = grayscale(source)
    gradient = _robust_normalize(ndi.gaussian_gradient_magnitude(gray, sigma=0.85), percentile=96.0)
    local_noise = _robust_normalize(np.abs(gray - ndi.gaussian_filter(gray, sigma=1.2)), percentile=97.0)
    boundary = ndi.binary_dilation(footprint, iterations=2) ^ ndi.binary_erosion(footprint, iterations=2)
    weak_boundary = ndi.gaussian_filter(boundary.astype(np.float32), sigma=1.0) * (1.0 - gradient)
    uncertainty = 0.14 * local_noise + 0.72 * weak_boundary

    labels, unresolved_ids = None, []
    resolved_ids = {
        int(item["region_id"])
        for item in applied_annotations
        if item.get("region_id") is not None
    }
    if lineart_labels is not None:
        labels = np.asarray(lineart_labels, dtype=np.int32)
        if labels.shape != footprint.shape:
            raise ValueError("line-art labels and mask must have the same shape")
        regions = list((lineart_report or {}).get("regions", []))
        largest = max((int(item.get("pixel_count", 0)) for item in regions), default=1)
        for item in regions:
            region_id = int(item["region_id"])
            region = labels == region_id
            if not region.any():
                continue
            if region_id in resolved_ids:
                uncertainty[region] *= 0.30
                continue
            unresolved_ids.append(region_id)
            smallness = 1.0 - min(int(item["pixel_count"]) / max(largest, 1), 1.0)
            uncertainty[region] = np.maximum(uncertainty[region], 0.46 + 0.22 * smallness)
            region_edge = ndi.binary_dilation(region) ^ ndi.binary_erosion(region)
            uncertainty[region_edge] = np.maximum(uncertainty[region_edge], 0.84)

    labels_islands, island_count = ndi.label(footprint)
    if island_count:
        areas = np.bincount(labels_islands.ravel())
        threshold = max(4, round(max(int(footprint.sum()), 1) * 0.0005))
        for island_id in range(1, int(island_count) + 1):
            if int(areas[island_id]) < threshold:
                uncertainty[labels_islands == island_id] = 1.0

    support = ndi.binary_dilation(footprint, iterations=3)
    uncertainty = np.where(support, np.clip(uncertainty, 0.0, 1.0), 0.0).astype(np.float32)
    samples = uncertainty[support]
    return uncertainty, {
        "mean_uncertainty": float(samples.mean()) if samples.size else 0.0,
        "high_uncertainty_fraction": float(np.mean(samples >= 0.65)) if samples.size else 0.0,
        "critical_uncertainty_fraction": float(np.mean(samples >= 0.82)) if samples.size else 0.0,
        "unresolved_region_ids": unresolved_ids,
        "unresolved_region_count": len(unresolved_ids),
        "interpretation": "review aid only; values are deterministic uncertainty estimates, not probabilities",
    }


def _colourize(values):
    field = np.clip(np.asarray(values, dtype=np.float32), 0.0, 1.0)
    anchors = np.asarray([[42, 132, 255], [57, 201, 150], [250, 210, 70], [244, 82, 72]], dtype=np.float32)
    scaled = field * 3.0
    lower = np.clip(np.floor(scaled).astype(np.int32), 0, 2)
    fraction = (scaled - lower)[..., None]
    return anchors[lower] * (1.0 - fraction) + anchors[lower + 1] * fraction


def save_uncertainty_preview(rgba, uncertainty, path, report=None):
    """Save a colour overlay and explicitly label it as an uncertainty aid."""
    source = np.asarray(rgba, dtype=np.uint8)
    values = np.asarray(uncertainty, dtype=np.float32)
    if source.shape[:2] != values.shape:
        raise ValueError("artwork and uncertainty map must have the same shape")
    colours = _colourize(values)
    alpha = np.clip(0.20 + values[..., None] * 0.62, 0.0, 0.82)
    output = source[:, :, :3].astype(np.float32) * (1.0 - alpha) + colours * alpha
    image = Image.fromarray(np.clip(output, 0, 255).astype(np.uint8), mode="RGB")
    draw = ImageDraw.Draw(image)
    legend_width = min(max(image.width // 3, 180), 360)
    x0, y0 = 12, max(image.height - 42, 4)
    for index in range(legend_width):
        colour = tuple(int(channel) for channel in _colourize([[index / max(legend_width - 1, 1)]])[0, 0])
        draw.line((x0 + index, y0, x0 + index, y0 + 10), fill=colour)
    draw.text((x0, y0 + 14), "stable", fill=(245, 245, 245))
    draw.text((x0 + legend_width, y0 + 14), "review", fill=(245, 245, 245), anchor="ra")
    if report:
        draw.text(
            (image.width - 12, 12),
            f"unresolved {int(report.get('unresolved_region_count', 0))}",
            fill=(255, 255, 255),
            anchor="ra",
            stroke_width=2,
            stroke_fill=(20, 22, 26),
        )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return str(target)
