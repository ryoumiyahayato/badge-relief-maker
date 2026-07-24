"""Quality mode presets for relief generation."""


QUALITY_PRESETS = {
    # Fidelity takes priority over low-end hardware. Preview keeps at least the
    # native grid for typical web images; export modes only downsample genuinely
    # large sources instead of collapsing text and engraving into tiny grids.
    # Tiny disconnected specks are removed because scans and line drawings often
    # contain JPEG dust that would otherwise become hundreds of loose micro-solids.
    "preview": {
        "max_grid_cells": 150000,
        "min_component_pixels": 8,
        "fill_hole_pixels": 8,
        "mask_smooth_iterations": 0,
    },
    "standard": {
        "max_grid_cells": 1000000,
        "min_component_pixels": 8,
        "fill_hole_pixels": 8,
        "mask_smooth_iterations": 0,
    },
    "high": {
        "max_grid_cells": 4000000,
        "min_component_pixels": 4,
        "fill_hole_pixels": 4,
        "mask_smooth_iterations": 0,
    },
}


def normalize_quality_mode(mode):
    """Return a known quality mode name."""
    value = str(mode or "standard").lower().strip()
    if value in {"low", "draft"}:
        return "preview"
    if value in {"hi", "export", "high_quality"}:
        return "high"
    if value not in QUALITY_PRESETS:
        return "standard"
    return value


def quality_preset(mode):
    """Return a copy of the preset for a quality mode."""
    normalized = normalize_quality_mode(mode)
    result = dict(QUALITY_PRESETS[normalized])
    result["quality_mode"] = normalized
    return result
