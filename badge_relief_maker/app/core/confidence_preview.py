"""Visual uncertainty estimates for manual relief review.

The map is not a classifier score. It is a deterministic review aid that marks
weak silhouette evidence, noisy local contrast, unresolved line-art regions and
small isolated components. The GUI uses it to direct the user toward places that
need explicit semantic annotation before mesh generation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi


def _grayscale(rgba):
    values = np.asarray(rgba, dtype=np.uint8)
    if values.ndim != 3 or values.shape[2] != 4:
        raise ValueError("expected an RGBA image")
    rgb = values[:, :, :3].astype(np.float32) / 255.0
    return (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]).astype(np.float32)


def _robust_normalize(values, percentile=95.0):
    array = np.asarray(values, dtype=np.float32)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros(array.shape, dtype=np.float32)
    scale = float(np.percentile(finite, float(percentile)))
    if scale <= 1e-8:
        return np.zeros(array.shape, dtype=np.float32)
    return np.clip(array / scale, 0.0, 1.0).astype(np.float32)


def build_uncertainty_map(
    rgba,
    mask,
    *,
    lineart_labels=None,
    lineart_report=None,
    override_report=None,
):
    """Return a 0..1 uncertainty field and a compact review report."""
    source = np.asarray(rgba, dtype=np.uint8)
    foreground = np.asarray(mask, dtype=bool)
    if source.shape[:2] != foreground.shape:
        raise ValueError("artwork and mask must have the same shape")

    gray = _grayscale(source)
    gradient = _robust_normalize(ndi.gaussian_gradient_magnitude(gray, sigma=0.85), percentile=96.0)
    local_texture = _robust_normalize(np.abs(gray - ndi.gaussian_filter(gray, sigma=1.2)), percentile=97.0)

    dilated = ndi.binary_dilation(foreground, iterations=2)
    eroded = ndi.binary_erosion(foreground, iterations=2)
    boundary = dilated ^ eroded
    boundary_band = ndi.gaussian_filter(boundary.astype(np.float32), sigma=1.0)
    boundary_uncertainty = boundary_band * (1.0 - gradient)

    uncertainty = 0.14 * local_texture + 0.78 * boundary_uncertainty
    review_support = ndi.binary_dilation(foreground, iterations=3)

    labels = None if lineart_labels is None else np.asarray(lineart_labels, dtype=np.int32)
    unresolved_region_ids = []
    resolved_region_ids = {
        int(item.get("region_id", -1))
        for item in (override_report or {}).get("applied", [])
        if isinstance(item, dict)
    }
    if labels is not None:
        if labels.shape != foreground.shape:
            raise ValueError("line-art labels and mask must have the same shape")
        reported = list((lineart_report or {}).get("regions", []))
        maximum_area = max((int(item.get("pixel_count", 0)) for item in reported), default=1)
        for item in reported:
            region_id = int(item.get("region_id", -1))
            region = labels == region_id
            if not region.any():
                continue
            if region_id in resolved_region_ids:
                uncertainty[region] *= 0.35
                continue
            unresolved_region_ids.append(region_id)
            area = max(int(item.get("pixel_count", int(region.sum()))), 1)
            smallness = 1.0 - min(float(area) / float(maximum_area), 1.0)
            region_score = 0.48 + 0.22 * smallness
            uncertainty[region] = np.maximum(uncertainty[region], region_score)
            region_edge = ndi.binary_dilation(region, iterations=1) ^ ndi.binary_erosion(region, iterations=1)
            uncertainty[region_edge] = np.maximum(uncertainty[region_edge], 0.82)

    uncertainty = np.where(review_support, np.clip(uncertainty, 0.0, 1.0), 0.0).astype(np.float32)
    supported = uncertainty[review_support]
    mean_score = float(supported.mean()) if supported.size else 0.0
    high_fraction = float(np.mean(supported >= 0.65)) if supported.size else 0.0
    critical_fraction = float(np.mean(supported >= 0.82)) if supported.size else 0.0
    return uncertainty, {
        "mean_uncertainty": mean_score,
        "high_uncertainty_fraction": high_fraction,
        "critical_uncertainty_fraction": critical_fraction,
        "unresolved_region_ids": unresolved_region_ids,
        "unresolved_region_count": len(unresolved_region_ids),
        "interpretation": "review aid; higher values indicate weaker or unresolved evidence",
    }


def _colourize(values):
    field = np.clip(np.asarray(values, dtype=np.float32), 0.0, 1.0)
    anchors = np.asarray(
        [
            [42, 132, 255],
            [57, 201, 150],
            [250, 210, 70],
            [244, 82, 72],
        ],
        dtype=np.float32,
    )
    scaled = field * 3.0
    lower = np.floor(scaled).astype(np.int32)
    lower = np.clip(lower, 0, 2)
    upper = lower + 1
    fraction = (scaled - lower)[..., None]
    return anchors[lower] * (1.0 - fraction) + anchors[upper] * fraction


def save_uncertainty_preview(rgba, uncertainty, path, report=None):
    """Save a colour overlay with a compact legend."""
    source = np.asarray(rgba, dtype=np.uint8)
    values = np.asarray(uncertainty, dtype=np.float32)
    if source.shape[:2] != values.shape:
        raise ValueError("artwork and uncertainty map must have the same shape")

    colours = _colourize(values)
    alpha = np.clip(0.20 + values[..., None] * 0.62, 0.0, 0.82)
    rgb = source[:, :, :3].astype(np.float32)
    output = rgb * (1.0 - alpha) + colours * alpha
    image = Image.fromarray(np.clip(output, 0, 255).astype(np.uint8), mode="RGB")

    draw = ImageDraw.Draw(image)
    legend_width = min(max(image.width // 3, 180), 360)
    legend_height = 30
    x0 = 12
    y0 = max(image.height - legend_height - 12, 4)
    for index in range(legend_width):
        value = index / max(legend_width - 1, 1)
        colour = tuple(int(channel) for channel in _colourize(np.asarray([[value]], dtype=np.float32))[0, 0])
        draw.line((x0 + index, y0, x0 + index, y0 + 10), fill=colour)
    draw.rectangle((x0 - 1, y0 - 1, x0 + legend_width, y0 + 11), outline=(235, 235, 235))
    draw.text((x0, y0 + 14), "稳定", fill=(245, 245, 245))
    draw.text((x0 + legend_width - 24, y0 + 14), "疑点", fill=(245, 245, 245), anchor="ra")
    if report:
        count = int(report.get("unresolved_region_count", 0))
        text = f"待确认区域 {count}"
        box = draw.textbbox((image.width - 12, 12), text, anchor="ra")
        draw.rectangle((box[0] - 5, box[1] - 3, box[2] + 5, box[3] + 3), fill=(20, 22, 26))
        draw.text((image.width - 12, 12), text, fill=(255, 255, 255), anchor="ra")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return str(output_path)


def save_focused_region_preview(base_preview_path, region, output_path):
    """Draw a visible box around one numbered region for guided review."""
    image = Image.open(base_preview_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = region.get("bbox_normalized", [0.0, 0.0, 1.0, 1.0])
    left = int(round(float(x0) * max(image.width - 1, 1)))
    top = int(round(float(y0) * max(image.height - 1, 1)))
    right = int(round(float(x1) * max(image.width - 1, 1)))
    bottom = int(round(float(y1) * max(image.height - 1, 1)))
    width = max(2, image.width // 240)
    for offset in range(width):
        draw.rectangle((left - offset, top - offset, right + offset, bottom + offset), outline=(255, 72, 64))
    label = f"待确认 #{region.get('display_id', '?')}"
    draw.rectangle((left, max(top - 22, 0), left + 98, max(top - 2, 20)), fill=(255, 72, 64))
    draw.text((left + 5, max(top - 20, 2)), label, fill=(255, 255, 255))
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return str(target)
