"""Foreground mask generation."""

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


def _border_background(luminance):
    if luminance.size == 0:
        return 0.0
    border = np.concatenate((luminance[0, :], luminance[-1, :], luminance[:, 0], luminance[:, -1]))
    return float(np.median(border)) if border.size else 0.0


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


def foreground_mask(rgba, mode="auto", alpha_threshold=1, luminance_threshold=20):
    """Resolve alpha/luminance foreground masking and report the selected mode."""
    rgba = _rgba_array(rgba)
    mode = str(mode or "auto").strip().lower()
    supported = {"auto", "alpha", "luminance", "luminance-dark", "luminance-light"}
    if mode not in supported:
        raise ValueError(f"unsupported mask mode: {mode}")

    if mode == "alpha":
        return alpha_mask(rgba, alpha_threshold), "alpha"
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

    contrast = luminance_mask(rgba, luminance_threshold, "contrast")
    if contrast.any():
        return contrast, "luminance"

    return alpha_mask(rgba, alpha_threshold), "alpha_fallback_uniform_opaque"
