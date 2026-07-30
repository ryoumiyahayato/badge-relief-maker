"""Quality mode presets for relief generation."""

from .options import QUALITY_MODES


QUALITY_PRESETS = {
    "preview": {
        "max_grid_cells": 5000,
        "min_component_pixels": 4,
        "fill_hole_pixels": 8,
        "mask_smooth_iterations": 1,
    },
    "standard": {
        "max_grid_cells": 20000,
        "min_component_pixels": 2,
        "fill_hole_pixels": 16,
        "mask_smooth_iterations": 0,
    },
    "high": {
        "max_grid_cells": 80000,
        "min_component_pixels": 1,
        "fill_hole_pixels": 8,
        "mask_smooth_iterations": 0,
    },
}


def normalize_quality_mode(mode):
    """Return a known quality mode name."""
    return QUALITY_MODES.normalize(mode)


def quality_preset(mode):
    """Return a copy of the preset for a quality mode."""
    normalized = normalize_quality_mode(mode)
    result = dict(QUALITY_PRESETS[normalized])
    result["quality_mode"] = normalized
    return result
