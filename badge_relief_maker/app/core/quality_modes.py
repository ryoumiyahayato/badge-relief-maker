"""Shared quality presets for regular and advanced relief generation."""


# The canonical user-facing names are draft/standard/fine. Legacy preview/high
# names remain first-class aliases so existing projects and reports stay stable.
_CANONICAL_PRESETS = {
    "draft": {
        "max_grid_cells": 250000,
        "min_component_pixels": 32,
        "fill_hole_pixels": 8,
        "mask_smooth_iterations": 0,
    },
    "standard": {
        "max_grid_cells": 1200000,
        "min_component_pixels": 32,
        "fill_hole_pixels": 8,
        "mask_smooth_iterations": 0,
    },
    "fine": {
        "max_grid_cells": 4800000,
        "min_component_pixels": 20,
        "fill_hole_pixels": 4,
        "mask_smooth_iterations": 0,
    },
}

QUALITY_PRESETS = {
    "draft": dict(_CANONICAL_PRESETS["draft"]),
    "preview": dict(_CANONICAL_PRESETS["draft"]),
    "standard": dict(_CANONICAL_PRESETS["standard"]),
    "fine": dict(_CANONICAL_PRESETS["fine"]),
    "high": dict(_CANONICAL_PRESETS["fine"]),
}

_QUALITY_ALIASES = {
    "low": "preview",
    "draft": "preview",
    "hi": "high",
    "fine": "high",
    "export": "high",
    "high_quality": "high",
    "normal": "standard",
}


def normalize_quality_mode(mode):
    """Return a stable known quality name while preserving legacy reports."""
    value = str(mode or "standard").lower().strip()
    value = _QUALITY_ALIASES.get(value, value)
    if value not in QUALITY_PRESETS:
        return "standard"
    return value


def quality_preset(mode):
    """Return one copy of the shared preset for a quality mode."""
    normalized = normalize_quality_mode(mode)
    result = dict(QUALITY_PRESETS[normalized])
    result["quality_mode"] = normalized
    result["canonical_quality_mode"] = {"preview": "draft", "high": "fine"}.get(normalized, normalized)
    return result
