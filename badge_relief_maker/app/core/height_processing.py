"""Global height processing and saved region-layer helpers."""

import numpy as np
from scipy import ndimage as ndi

from .height_markers import apply_manual_height_markers, manual_height_marker_region, normalize_manual_height_marker


def mean_filter(heightmap, mask=None):
    """Return a 3x3 mean without allowing void/background pixels to bleed in."""
    values = np.asarray(heightmap, dtype=float)
    if mask is None:
        weights = np.ones(values.shape, dtype=float)
    else:
        weights = np.asarray(mask, dtype=bool).astype(float)
        if weights.shape != values.shape:
            raise ValueError("heightmap and mask must have the same shape")
    padded_values = np.pad(values * weights, 1, mode="constant")
    padded_weights = np.pad(weights, 1, mode="constant")
    total = np.zeros_like(values)
    count = np.zeros_like(values)
    for row_offset in range(3):
        for col_offset in range(3):
            total += padded_values[row_offset : row_offset + values.shape[0], col_offset : col_offset + values.shape[1]]
            count += padded_weights[row_offset : row_offset + values.shape[0], col_offset : col_offset + values.shape[1]]
    return np.divide(total, np.maximum(count, 1.0))


def masked_gaussian(heightmap, mask, sigma):
    """Gaussian blur normalized by foreground support so holes stay sharp."""
    values = np.asarray(heightmap, dtype=float)
    weights = np.asarray(mask, dtype=bool).astype(float)
    numerator = ndi.gaussian_filter(values * weights, sigma=float(sigma), mode="constant")
    denominator = ndi.gaussian_filter(weights, sigma=float(sigma), mode="constant")
    return np.divide(numerator, denominator, out=values.copy(), where=denominator > 1e-8)


def refine_heightmap(heightmap, mask, smooth_strength=0.0, detail_sharpness=0.0):
    values = np.asarray(heightmap, dtype=float).copy()
    foreground = np.asarray(mask, dtype=bool)
    smooth = float(np.clip(smooth_strength, 0.0, 1.0))
    sharp = float(np.clip(detail_sharpness, 0.0, 1.0))
    blurred = mean_filter(values, foreground)
    if smooth > 0.0:
        values[foreground] = values[foreground] * (1.0 - smooth) + blurred[foreground] * smooth
    if sharp > 0.0:
        reference = mean_filter(values, foreground)
        values[foreground] = values[foreground] + sharp * (values[foreground] - reference[foreground])
    values = np.where(foreground, np.clip(values, 0.0, 1.0), 0.0)
    return values.astype(np.float32), {"smooth_strength": smooth, "detail_sharpness": sharp}


def _component_profile(region, exponent=0.72):
    """Return a 0..1 rounded profile normalized per connected component."""
    region = np.asarray(region, dtype=bool)
    labels, count = ndi.label(region)
    profile = np.zeros(region.shape, dtype=float)
    for label_id in range(1, int(count) + 1):
        component = labels == label_id
        distance = ndi.distance_transform_edt(component)
        maximum = float(distance.max())
        if maximum <= 0.0:
            profile[component] = 1.0
        else:
            profile[component] = np.power(np.clip(distance[component] / maximum, 0.0, 1.0), float(exponent))
    return profile


def _boundary_reference(values, foreground, region):
    near = ndi.binary_dilation(region, iterations=2)
    far = ndi.binary_dilation(region, iterations=8)
    ring = far & ~near & foreground & ~region
    sample = np.asarray(values, dtype=float)[ring]
    if sample.size:
        return float(np.percentile(sample, 60.0))
    sample = np.asarray(values, dtype=float)[foreground & ~region]
    return float(np.median(sample)) if sample.size else 0.0


def _float(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    return result if np.isfinite(result) else float(default)


def _rounded_layer(result, foreground, region, layer, normalized):
    operation = str(normalized.get("operation", "set")).lower()
    peak = float(normalized.get("value", 0.0))
    exponent = max(_float(layer.get("profile_exponent", layer.get("roundness", 0.72)), 0.72), 0.05)
    profile = _component_profile(region, exponent=exponent)

    if "base_height_normalized" in layer:
        base = float(np.clip(_float(layer.get("base_height_normalized"), 0.0), 0.0, 1.0))
    else:
        base = _boundary_reference(result, foreground, region)

    if operation == "add":
        target = np.clip(result + peak * profile, 0.0, 1.0)
    elif operation == "subtract":
        target = np.clip(result - peak * profile, 0.0, 1.0)
    else:
        target = np.clip(base + (peak - base) * profile, 0.0, 1.0)

    detail_mix = float(np.clip(_float(layer.get("detail_mix", 0.12), 0.12), 0.0, 1.0))
    if detail_mix > 0.0:
        sigma = max(_float(layer.get("detail_sigma", 2.0), 2.0), 0.1)
        detail = result - masked_gaussian(result, foreground, sigma=sigma)
        target = np.clip(target + detail * detail_mix, 0.0, 1.0)
    return target


def apply_region_layers(heightmap, mask, layers=()):
    """Apply ordered marker-shaped layers and return a lock mask.

    Layers support the historical flat behaviour plus ``profile='rounded'`` (or
    ``domed``/``ridge``). A rounded layer uses the selected shape only as a
    footprint; its boundary remains near the carrier surface and its interior rises
    smoothly to the requested peak. This is suitable for medal rims, ribbons,
    leaves, shields and other broad components without flattening the engraved
    detail already present in the source height field.
    """
    result = np.asarray(heightmap, dtype=float).copy()
    foreground = np.asarray(mask, dtype=bool)
    locked = np.zeros(foreground.shape, dtype=bool)
    requested = 0
    applied = 0
    rounded = 0
    for layer in layers or ():
        requested += 1
        if not isinstance(layer, dict):
            continue
        marker = dict(layer)
        marker.setdefault("operation", "set")
        if not any(key in marker for key in ("height_normalized", "normalized_height", "height", "value", "delta")):
            continue
        normalized = normalize_manual_height_marker(marker, foreground.shape)
        if normalized is None:
            continue
        region = manual_height_marker_region(foreground, marker)
        if not region.any():
            continue

        profile_name = str(layer.get("profile", layer.get("surface_profile", "flat"))).strip().lower()
        if profile_name in {"rounded", "round", "domed", "dome", "ridge", "convex"}:
            candidate = _rounded_layer(result, foreground, region, layer, normalized)
            rounded += 1
        else:
            candidate, marker_report = apply_manual_height_markers(result, foreground, marker)
            if not marker_report["applied_marker_count"]:
                continue

        feather_px = layer.get("feather_px")
        if feather_px is None and "feather_normalized" in layer:
            feather_px = _float(layer.get("feather_normalized"), 0.0) * min(foreground.shape)
        feather_px = max(_float(feather_px, 0.0), 0.0)
        if feather_px > 0.0:
            distance = ndi.distance_transform_edt(region)
            weight = np.clip(distance / feather_px, 0.0, 1.0)
            result[region] = result[region] * (1.0 - weight[region]) + candidate[region] * weight[region]
        else:
            result[region] = candidate[region]
        applied += 1
        if bool(layer.get("locked", False)):
            locked |= region

    result = np.where(foreground, np.clip(result, 0.0, 1.0), 0.0)
    return result.astype(np.float32), locked, {
        "requested_layer_count": requested,
        "applied_layer_count": applied,
        "rounded_layer_count": rounded,
        "locked_pixel_count": int(locked.sum()),
    }
