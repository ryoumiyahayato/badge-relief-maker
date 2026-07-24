"""Foreground mask generation."""

from collections import deque

import numpy as np


def _rgba_array(rgba):
    rgba = np.asarray(rgba)
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("expected rgba image")
    return rgba


def _luminance(rgba):
    rgba = _rgba_array(rgba)
    rgb = rgba[:, :, :3].astype(np.float32)
    return 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]


def _border_pixels(values):
    if values.size == 0:
        return np.empty((0,) + values.shape[2:], dtype=values.dtype)
    return np.concatenate((values[0, ...], values[-1, ...], values[:, 0, ...], values[:, -1, ...]), axis=0)


def _border_background(luminance):
    border = _border_pixels(np.asarray(luminance))
    return float(np.median(border)) if border.size else 0.0


def _flood_border_candidates(candidates):
    """Return candidate pixels connected to any image border pixel."""
    candidates = np.asarray(candidates, dtype=bool)
    height, width = candidates.shape
    connected = np.zeros_like(candidates, dtype=bool)
    queue = deque()

    def add(y, x):
        if candidates[y, x] and not connected[y, x]:
            connected[y, x] = True
            queue.append((y, x))

    for x in range(width):
        add(0, x)
        if height > 1:
            add(height - 1, x)
    for y in range(height):
        add(y, 0)
        if width > 1:
            add(y, width - 1)

    while queue:
        y, x = queue.popleft()
        if y > 0:
            add(y - 1, x)
        if y + 1 < height:
            add(y + 1, x)
        if x > 0:
            add(y, x - 1)
        if x + 1 < width:
            add(y, x + 1)
    return connected


def alpha_mask(rgba: np.ndarray, threshold: int = 1) -> np.ndarray:
    """Create a foreground mask from an alpha channel."""
    rgba = _rgba_array(rgba)
    return rgba[:, :, 3] >= int(threshold)


def luminance_mask(rgba: np.ndarray, threshold: int = 20, polarity="contrast") -> np.ndarray:
    """Create a mask from brightness relative to the image-border background.

    ``contrast`` supports either dark-on-light or light-on-dark artwork. The
    explicit ``dark`` and ``light`` polarities are useful when the border contains
    known background but low-contrast details must not be selected from both sides.
    """
    luminance = _luminance(rgba)
    background = _border_background(luminance)
    threshold = max(0.0, float(threshold))
    polarity = str(polarity or "contrast").strip().lower()
    if polarity == "contrast":
        return np.abs(luminance - background) >= threshold
    if polarity == "dark":
        return luminance <= background - threshold
    if polarity == "light":
        return luminance >= background + threshold
    raise ValueError("luminance polarity must be 'contrast', 'dark' or 'light'")


def border_connected_background_mask(rgba, threshold=20):
    """Extract an opaque object silhouette from a mostly uniform background.

    A plain luminance threshold turns white lettering and pale artwork inside a
    badge into holes. Instead, this method estimates the border colour and removes
    only background-like pixels that are actually connected to the image border.
    Enclosed light regions therefore remain part of the physical badge footprint.
    """
    rgba = _rgba_array(rgba)
    rgb = rgba[:, :, :3].astype(np.float32)
    border = _border_pixels(rgb)
    if border.size == 0:
        return np.ones(rgba.shape[:2], dtype=bool)

    reference = np.median(border, axis=0)
    border_distance = np.sqrt(np.mean((border - reference) ** 2, axis=1))
    adaptive_threshold = max(float(threshold), float(np.percentile(border_distance, 95)) + 8.0)
    distance = np.sqrt(np.mean((rgb - reference) ** 2, axis=2))
    background_candidates = distance <= adaptive_threshold
    connected_background = _flood_border_candidates(background_candidates)
    return ~connected_background


def foreground_mask(rgba, mode="auto", alpha_threshold=1, luminance_threshold=20):
    """Resolve alpha/background/luminance masking and report the selected mode."""
    rgba = _rgba_array(rgba)
    mode = str(mode or "auto").strip().lower()
    supported = {"auto", "alpha", "background", "luminance", "luminance-dark", "luminance-light"}
    if mode not in supported:
        raise ValueError(f"unsupported mask mode: {mode}")

    if mode == "alpha":
        return alpha_mask(rgba, alpha_threshold), "alpha"
    if mode == "background":
        return border_connected_background_mask(rgba, luminance_threshold), "background"
    if mode == "luminance":
        return luminance_mask(rgba, luminance_threshold, "contrast"), "luminance"
    if mode == "luminance-dark":
        return luminance_mask(rgba, luminance_threshold, "dark"), "luminance-dark"
    if mode == "luminance-light":
        return luminance_mask(rgba, luminance_threshold, "light"), "luminance-light"

    alpha = rgba[:, :, 3]
    visible = alpha >= int(alpha_threshold)
    if not np.any(visible):
        return alpha_mask(rgba, alpha_threshold), "alpha"

    alpha_is_informative = bool(alpha.size and int(alpha.min()) < int(alpha.max()))
    if alpha_is_informative:
        return alpha_mask(rgba, alpha_threshold), "alpha"

    silhouette = border_connected_background_mask(rgba, luminance_threshold)
    foreground_fraction = float(silhouette.mean()) if silhouette.size else 0.0
    contrast = luminance_mask(rgba, luminance_threshold, "contrast")

    # Preserve the established luminance result for simple isolated dark/light
    # marks. Switch to the silhouette method only when it recovers a meaningful
    # amount of enclosed pale artwork that a raw contrast threshold would punch
    # out as holes.
    recovered = int(np.count_nonzero(silhouette & ~contrast))
    recovery_threshold = max(4, int(np.count_nonzero(silhouette) * 0.03))
    if silhouette.any() and foreground_fraction < 0.98 and recovered >= recovery_threshold:
        return silhouette, "background"
    if contrast.any():
        return contrast, "luminance"
    if silhouette.any() and foreground_fraction < 0.98:
        return silhouette, "background"

    return alpha_mask(rgba, alpha_threshold), "alpha_fallback_uniform_opaque"
