"""Quality mode presets for relief generation."""

from .options import QUALITY_MODES


QUALITY_PRESETS = {
    "preview": {
        "max_grid_cells": 250000,
        "min_component_pixels": 32,
        "fill_hole_pixels": 8,
        "mask_smooth_iterations": 0,
        "adaptive_coarse_cell_px": 8,
    },
    "standard": {
        "max_grid_cells": 1200000,
        "min_component_pixels": 32,
        "fill_hole_pixels": 8,
        "mask_smooth_iterations": 0,
        "adaptive_coarse_cell_px": 4,
    },
    "high": {
        "max_grid_cells": 4800000,
        "min_component_pixels": 20,
        "fill_hole_pixels": 4,
        "mask_smooth_iterations": 0,
        "adaptive_coarse_cell_px": 2,
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
