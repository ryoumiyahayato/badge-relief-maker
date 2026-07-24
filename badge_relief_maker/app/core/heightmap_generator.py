"""Heightmap generation from artwork."""

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi


def empty_heightmap(shape):
    """Create an empty heightmap for tests and early wiring."""
    return np.zeros(shape, dtype=np.float32)


def flat_heightmap(mask, value=0.55):
    """Create a safe, uniform relief plateau inside the object footprint."""
    foreground = np.asarray(mask, dtype=bool)
    return np.where(foreground, np.clip(float(value), 0.0, 1.0), 0.0).astype(np.float32)


def _grayscale(rgba):
    rgba = np.asarray(rgba)
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("expected rgba image")
    rgb = rgba[:, :, :3].astype(np.float32) / 255.0
    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    return rgb, gray.astype(np.float32)


def classify_artwork(rgba, mask):
    """Classify the input as line artwork or continuous-tone artwork.

    Line drawings need a different interpretation from photographs. Treating white
    paper as maximum physical height creates an engraved flat plate rather than a
    sculptural medal. JPEG antialiasing and dense hatching create many intermediate
    gray pixels, so the threshold accepts a strongly near-binary achromatic image
    without requiring every stroke to remain pure black or white.
    """
    rgb, gray = _grayscale(rgba)
    foreground = np.asarray(mask, dtype=bool)
    if foreground.shape != gray.shape:
        raise ValueError("mask and image must have the same height and width")
    sample = gray[foreground]
    if sample.size == 0:
        return "empty"
    near_binary = float(np.mean((sample <= 0.22) | (sample >= 0.78)))
    ink_fraction = float(np.mean(sample < 0.50))
    chroma = np.max(rgb, axis=2) - np.min(rgb, axis=2)
    mean_chroma = float(np.mean(chroma[foreground]))
    if near_binary >= 0.64 and 0.015 <= ink_fraction <= 0.72 and mean_chroma <= 0.08:
        return "lineart"
    return "continuous_tone"


def grayscale_heightmap(rgba, mask=None, invert=False, uniform_value=1.0):
    """Convert image brightness to a normalized foreground heightmap.

    Foreground normalization ignores background pixels. A uniformly bright
    foreground has no recoverable relative depth, so the deterministic default is
    a constant full-height value of 1.0 before optional inversion. This produces a
    usable raised plateau while still satisfying ``inverted = 1 - normal``.
    """
    _, gray = _grayscale(rgba)

    if mask is None:
        sample = gray.reshape(-1)
        foreground = None
    else:
        foreground = np.asarray(mask, dtype=bool)
        if foreground.shape != gray.shape:
            raise ValueError("mask and image must have the same height and width")
        sample = gray[foreground]

    result = np.zeros_like(gray, dtype=np.float32)
    if sample.size:
        low = float(sample.min())
        high = float(sample.max())
        if high > low:
            normalized = (gray - low) / (high - low)
        else:
            normalized = np.full_like(gray, np.clip(float(uniform_value), 0.0, 1.0), dtype=np.float32)
        if invert:
            normalized = 1.0 - normalized
        result = normalized.astype(np.float32)

    if foreground is not None:
        result = np.where(foreground, result, 0.0)
    return result.astype(np.float32)


def _blur_channel(values, radius):
    """Blur one normalized channel without introducing another code path."""
    image = Image.fromarray(np.clip(np.asarray(values) * 255.0, 0, 255).astype(np.uint8), mode="L")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius=float(radius))), dtype=np.float32) / 255.0


def _robust_normalize(values, foreground, percentile=99.0):
    values = np.asarray(values, dtype=np.float32)
    foreground = np.asarray(foreground, dtype=bool)
    sample = values[foreground]
    scale = float(np.percentile(sample, percentile)) if sample.size else 0.0
    return np.clip(values / max(scale, 1e-6), 0.0, 1.0).astype(np.float32)


def _continuous_tone_emboss(rgb, gray, foreground, base_level, detail_strength):
    sample = gray[foreground]
    low = float(np.percentile(sample, 1.0))
    high = float(np.percentile(sample, 99.0))
    if high > low + 1e-6:
        macro = np.clip((gray - low) / (high - low), 0.0, 1.0)
        macro = np.power(macro, 0.92).astype(np.float32)
    else:
        macro = np.ones_like(gray, dtype=np.float32)

    fine = gray - _blur_channel(gray, 0.55)
    medium = gray - _blur_channel(gray, 1.25)
    broad = gray - _blur_channel(gray, 2.75)
    signed_detail = 0.55 * fine + 0.30 * medium + 0.15 * broad
    absolute_sample = np.abs(signed_detail[foreground])
    detail_scale = float(np.percentile(absolute_sample, 99.0)) if absolute_sample.size else 0.0
    signed_detail = np.clip(signed_detail / max(detail_scale, 1e-6), -1.0, 1.0)

    smooth_rgb = np.stack([_blur_channel(rgb[:, :, channel], 0.65) for channel in range(3)], axis=2)
    gradient_y = np.gradient(smooth_rgb, axis=0)
    gradient_x = np.gradient(smooth_rgb, axis=1)
    colour_edge = np.sqrt(np.sum(gradient_x * gradient_x + gradient_y * gradient_y, axis=2))
    colour_edge = _robust_normalize(colour_edge, foreground, 99.0)

    floor_control = np.clip(float(base_level), 0.0, 1.0)
    floor = 0.02 + 0.10 * floor_control
    strength = np.clip(float(detail_strength), 0.0, 1.0)
    macro = floor + (1.0 - floor) * macro
    signed_gain = 0.035 + 0.065 * strength
    edge_gain = 0.025 + 0.055 * strength
    return np.clip(macro + signed_gain * signed_detail + edge_gain * colour_edge, 0.0, 1.0)


def _lineart_sculptural_emboss(gray, foreground, base_level, detail_strength):
    """Create a conservative, smooth line-art bas-relief base.

    The broad silhouette supplies only a shallow carrier form. Dark marks are
    separated by estimated stroke width: thick contours become structural grooves,
    while fine hatching and engraving remain much shallower. Enclosed white regions
    stay neutral until the boundary-aware region tools assign an explicit role.
    """
    minimum_dimension = float(max(min(gray.shape), 1))
    ink = np.clip((0.90 - gray) / 0.90, 0.0, 1.0) * foreground

    distance = ndi.distance_transform_edt(foreground)
    global_dome = np.power(_robust_normalize(distance, foreground, 99.0), 0.68)
    global_dome = ndi.gaussian_filter(global_dome, sigma=max(1.0, minimum_dimension / 420.0))

    # Estimate local stroke width from a conservative binary ink core. Thick
    # outlines carry structure; one-pixel hatching should not turn a medal into a
    # rough woodcut surface.
    ink_core = (ink >= 0.48) & foreground
    half_width = ndi.distance_transform_edt(ink_core)
    structural_weight = np.clip((half_width - 0.65) / 1.9, 0.0, 1.0)
    structural_ink = ndi.gaussian_filter(ink * structural_weight, sigma=0.65)
    fine_ink = ndi.gaussian_filter(ink * (1.0 - structural_weight), sigma=0.40)
    structural_ink = _robust_normalize(structural_ink, foreground, 99.5)
    fine_ink = _robust_normalize(fine_ink, foreground, 99.7)

    floor = 0.055 + 0.10 * np.clip(float(base_level), 0.0, 1.0)
    base = floor + 0.20 + 0.18 * global_dome
    strength = np.clip(float(detail_strength), 0.0, 1.0)
    structural_depth = 0.045 + 0.045 * strength
    fine_depth = 0.0025 + 0.0065 * strength
    result = base - structural_depth * structural_ink - fine_depth * fine_ink

    # Very light mask-aware smoothing removes JPEG stair-stepping without erasing
    # the structural grooves or crossing true holes.
    weights = foreground.astype(np.float32)
    sigma = max(0.45, minimum_dimension / 900.0)
    numerator = ndi.gaussian_filter(result * weights, sigma=sigma, mode="constant")
    denominator = ndi.gaussian_filter(weights, sigma=sigma, mode="constant")
    smoothed = np.divide(numerator, denominator, out=result.copy(), where=denominator > 1e-8)
    result = 0.70 * result + 0.30 * smoothed
    return np.clip(result, 0.0, 1.0)


def emboss_heightmap(rgba, mask, base_level=0.05, detail_strength=0.95, invert=False):
    """Create a general medal/badge bas-relief height field.

    Continuous-tone artwork follows robust grayscale and colour boundaries. Nearly
    binary line artwork uses a conservative path: ink becomes engraving, while
    enclosed white regions remain neutral until boundary roles are confirmed.
    """
    rgb, gray = _grayscale(rgba)
    foreground = np.asarray(mask, dtype=bool)
    if foreground.shape != gray.shape:
        raise ValueError("mask and image must have the same height and width")
    if not foreground.any():
        return np.zeros(foreground.shape, dtype=np.float32)

    interpretation = classify_artwork(rgba, foreground)
    if interpretation == "lineart":
        result = _lineart_sculptural_emboss(gray, foreground, base_level, detail_strength)
    else:
        result = _continuous_tone_emboss(rgb, gray, foreground, base_level, detail_strength)

    if invert:
        result = 1.0 - result
    return np.where(foreground, result, 0.0).astype(np.float32)


def layered_heightmap(regions, heights, shape):
    """Assign fixed heights to region masks."""
    result = np.zeros(shape, dtype=np.float32)
    for region, height in zip(regions, heights):
        result[region.astype(bool)] = float(height)
    return result
