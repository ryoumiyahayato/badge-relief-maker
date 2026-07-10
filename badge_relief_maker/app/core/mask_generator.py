"""Foreground mask generation."""

import numpy as np


def _luminance(rgba):
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("expected rgba image")
    rgb = rgba[:, :, :3].astype(np.float32)
    return 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]


def alpha_mask(rgba: np.ndarray, threshold: int = 1) -> np.ndarray:
    """Create a foreground mask from an alpha channel."""
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("expected rgba image")
    return rgba[:, :, 3] >= int(threshold)


def luminance_mask(rgba: np.ndarray, threshold: int = 20) -> np.ndarray:
    """Create a foreground mask from brightness contrast against the image border.

    This supports both dark artwork on a light background and light artwork on a
    dark background. It is intentionally lightweight and assumes the image border
    is mostly background.
    """
    luminance = _luminance(rgba)
    border = np.concatenate((luminance[0, :], luminance[-1, :], luminance[:, 0], luminance[:, -1]))
    background = float(np.median(border)) if border.size else 0.0
    return np.abs(luminance - background) >= max(0.0, float(threshold))


def foreground_mask(rgba, mode="auto", alpha_threshold=1, luminance_threshold=20):
    """Resolve alpha/luminance foreground masking and report the selected mode."""
    mode = str(mode or "auto").strip().lower()
    if mode not in {"auto", "alpha", "luminance"}:
        raise ValueError(f"unsupported mask mode: {mode}")

    if mode == "alpha":
        return alpha_mask(rgba, alpha_threshold), "alpha"
    if mode == "luminance":
        return luminance_mask(rgba, luminance_threshold), "luminance"

    alpha = np.asarray(rgba)[:, :, 3]
    visible = alpha >= int(alpha_threshold)
    if not np.any(visible):
        return alpha_mask(rgba, alpha_threshold), "alpha"

    alpha_is_informative = bool(alpha.size and int(alpha.min()) < int(alpha.max()))
    if alpha_is_informative:
        return alpha_mask(rgba, alpha_threshold), "alpha"

    contrast = luminance_mask(rgba, luminance_threshold)
    if contrast.any():
        return contrast, "luminance"

    return alpha_mask(rgba, alpha_threshold), "alpha_fallback_uniform_opaque"
