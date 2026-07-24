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


def emboss_heightmap(rgba, mask, base_level=0.28, detail_strength=0.72, invert=False):
    """Create a restrained automatic relief from edges and local detail.

    Badge artwork colours are not reliable depth labels. Mapping raw brightness
    directly to Z makes white paint protrude and black print collapse. This mode
    instead creates a stable base plateau and raises local colour/texture edges,
    which preserves lettering, borders and ornament without pretending that colour
    alone defines physical depth.
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
    smooth_image = Image.fromarray(np.clip(rgb * 255.0, 0, 255).astype(np.uint8), mode="RGB")
    smooth = np.asarray(smooth_image.filter(ImageFilter.GaussianBlur(radius=0.8)), dtype=np.float32) / 255.0

    gradient_y = np.gradient(smooth, axis=0)
    gradient_x = np.gradient(smooth, axis=1)
    colour_edge = np.sqrt(np.sum(gradient_x * gradient_x + gradient_y * gradient_y, axis=2))

    gray = 0.2126 * smooth[:, :, 0] + 0.7152 * smooth[:, :, 1] + 0.0722 * smooth[:, :, 2]
    local_blur = np.asarray(
        Image.fromarray(np.clip(gray * 255.0, 0, 255).astype(np.uint8), mode="L").filter(ImageFilter.GaussianBlur(radius=2.0)),
        dtype=np.float32,
    ) / 255.0
    local_detail = np.abs(gray - local_blur)
    detail = colour_edge * 1.2 + local_detail * 1.8

    sample = detail[foreground]
    robust_high = float(np.percentile(sample, 98)) if sample.size else 0.0
    detail = np.clip(detail / max(robust_high, 1e-6), 0.0, 1.0)
    detail_image = Image.fromarray(np.clip(detail * 255.0, 0, 255).astype(np.uint8), mode="L")
    detail = np.asarray(
        detail_image.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(radius=0.6)), dtype=np.float32
    ) / 255.0

    base = np.clip(float(base_level), 0.0, 1.0)
    strength = np.clip(float(detail_strength), 0.0, 1.0)
    result = base + strength * detail
    if invert:
        result = 1.0 - result
    return np.where(foreground, np.clip(result, 0.0, 1.0), 0.0).astype(np.float32)


def layered_heightmap(regions, heights, shape):
    """Assign fixed heights to region masks."""
    result = np.zeros(shape, dtype=np.float32)
    for region, height in zip(regions, heights):
        result[region.astype(bool)] = float(height)
    return result
