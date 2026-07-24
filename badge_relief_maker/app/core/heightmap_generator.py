"""Heightmap generation from artwork."""

import numpy as np
from PIL import Image, ImageFilter


def empty_heightmap(shape):
    """Create an empty heightmap for tests and early wiring."""
    return np.zeros(shape, dtype=np.float32)


def flat_heightmap(mask, value=0.55):
    """Create a safe, uniform relief plateau inside the object footprint."""
    foreground = np.asarray(mask, dtype=bool)
    return np.where(foreground, np.clip(float(value), 0.0, 1.0), 0.0).astype(np.float32)


def grayscale_heightmap(rgba, mask=None, invert=False, uniform_value=1.0):
    """Convert image brightness to a normalized foreground heightmap.

    Foreground normalization ignores background pixels. A uniformly bright
    foreground has no recoverable relative depth, so the deterministic default is
    a constant full-height value of 1.0 before optional inversion. This produces a
    usable raised plateau while still satisfying ``inverted = 1 - normal``.
    """
    rgba = np.asarray(rgba)
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("expected rgba image")
    rgb = rgba[:, :, :3].astype(np.float32)
    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]

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
    """Blur one normalized channel without introducing an extra dependency."""
    image = Image.fromarray(np.clip(np.asarray(values) * 255.0, 0, 255).astype(np.uint8), mode="L")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius=float(radius))), dtype=np.float32) / 255.0


def emboss_heightmap(rgba, mask, base_level=0.05, detail_strength=0.95, invert=False):
    """Create a general high-fidelity medal/badge relief height field.

    The low-frequency surface follows robust foreground grayscale because that is
    the most reproducible depth cue available in scans and photographs of medals,
    badges and plaques. Fine lettering, engraving, guilloche, wreath texture and
    colour boundaries are restored separately with a signed multi-scale detail
    pyramid. This preserves the overall grayscale relationship instead of replacing
    it with a flat plateau, while avoiding object-specific rules for any one badge.
    """
    rgba = np.asarray(rgba)
    foreground = np.asarray(mask, dtype=bool)
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("expected rgba image")
    if foreground.shape != rgba.shape[:2]:
        raise ValueError("mask and image must have the same height and width")
    if not foreground.any():
        return np.zeros(foreground.shape, dtype=np.float32)

    rgb = rgba[:, :, :3].astype(np.float32) / 255.0
    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    sample = gray[foreground]
    low = float(np.percentile(sample, 1.0))
    high = float(np.percentile(sample, 99.0))
    if high > low + 1e-6:
        macro = np.clip((gray - low) / (high - low), 0.0, 1.0)
        macro = np.power(macro, 0.92).astype(np.float32)
    else:
        macro = np.ones_like(gray, dtype=np.float32)

    # Signed detail keeps dark incisions dark and bright ridges bright. Several
    # radii cover thin text, medium ornament and broader embossed transitions.
    fine = gray - _blur_channel(gray, 0.55)
    medium = gray - _blur_channel(gray, 1.25)
    broad = gray - _blur_channel(gray, 2.75)
    signed_detail = 0.55 * fine + 0.30 * medium + 0.15 * broad
    absolute_sample = np.abs(signed_detail[foreground])
    detail_scale = float(np.percentile(absolute_sample, 99.0)) if absolute_sample.size else 0.0
    signed_detail = np.clip(signed_detail / max(detail_scale, 1e-6), -1.0, 1.0)

    # Two colours can have nearly identical luminance. A small chroma-boundary
    # ridge keeps enamel dividers and printed outlines visible without changing the
    # large-scale grayscale depth ordering.
    smooth_rgb = np.stack([_blur_channel(rgb[:, :, channel], 0.65) for channel in range(3)], axis=2)
    gradient_y = np.gradient(smooth_rgb, axis=0)
    gradient_x = np.gradient(smooth_rgb, axis=1)
    colour_edge = np.sqrt(np.sum(gradient_x * gradient_x + gradient_y * gradient_y, axis=2))
    edge_sample = colour_edge[foreground]
    edge_scale = float(np.percentile(edge_sample, 99.0)) if edge_sample.size else 0.0
    colour_edge = np.clip(colour_edge / max(edge_scale, 1e-6), 0.0, 1.0)

    floor_control = np.clip(float(base_level), 0.0, 1.0)
    floor = 0.02 + 0.10 * floor_control
    strength = np.clip(float(detail_strength), 0.0, 1.0)
    macro = floor + (1.0 - floor) * macro
    signed_gain = 0.035 + 0.065 * strength
    edge_gain = 0.025 + 0.055 * strength
    result = np.clip(macro + signed_gain * signed_detail + edge_gain * colour_edge, 0.0, 1.0)
    if invert:
        result = 1.0 - result
    return np.where(foreground, result, 0.0).astype(np.float32)


def layered_heightmap(regions, heights, shape):
    """Assign fixed heights to region masks."""
    result = np.zeros(shape, dtype=np.float32)
    for region, height in zip(regions, heights):
        result[region.astype(bool)] = float(height)
    return result
