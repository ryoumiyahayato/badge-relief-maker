"""Front and back relief combination helpers."""


def align_placeholder(front_heightmap, back_heightmap):
    """Placeholder for manual front/back alignment."""
    if front_heightmap.shape != back_heightmap.shape:
        raise ValueError("front and back heightmaps must have the same shape")
    return front_heightmap, back_heightmap
