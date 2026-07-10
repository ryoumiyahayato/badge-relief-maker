"""Build a closed rectangular relief solid from a heightmap."""

import numpy as np

from .masked_solid_builder import build_masked_relief_solid


def build_rectangular_relief_solid(heightmap, width_mm, height_mm, base_thickness_mm, relief_height_mm):
    """Create a closed rectangular solid with a raised top relief surface.

    The rectangle path uses the same shared-vertex, height-slab implementation as
    the masked footprint builder with an all-foreground mask. This keeps winding,
    edge closure and one-pixel inputs consistent across both build modes.
    """
    heightmap = np.asarray(heightmap, dtype=float)
    if heightmap.ndim != 2:
        raise ValueError("heightmap must be a 2D array")
    if heightmap.size == 0:
        raise ValueError("heightmap must be a non-empty 2D array")
    mask = np.ones(heightmap.shape, dtype=bool)
    return build_masked_relief_solid(
        heightmap,
        mask,
        width_mm,
        height_mm,
        base_thickness_mm,
        relief_height_mm,
    )
