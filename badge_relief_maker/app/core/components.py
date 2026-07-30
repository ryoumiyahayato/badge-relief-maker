"""Deterministic connected-component primitives for binary image grids."""

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PixelComponent:
    """One connected set of row/column pixels."""

    pixels: tuple[tuple[int, int], ...]
    touches_border: bool


def connected_components(mask, *, target=True, connectivity=4):
    """Return row-major connected components for target-valued pixels."""
    values = np.asarray(mask, dtype=bool)
    if values.ndim != 2:
        raise ValueError("mask must be a 2D array")
    if connectivity not in {4, 8}:
        raise ValueError("connectivity must be 4 or 8")

    offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))
    if connectivity == 8:
        offsets += ((-1, -1), (-1, 1), (1, -1), (1, 1))
    rows, cols = values.shape
    visited = np.zeros(values.shape, dtype=bool)
    components = []
    target = bool(target)

    for start_row in range(rows):
        for start_col in range(cols):
            if visited[start_row, start_col] or bool(values[start_row, start_col]) != target:
                continue
            visited[start_row, start_col] = True
            queue = deque(((start_row, start_col),))
            pixels = []
            touches_border = False
            while queue:
                row, col = queue.popleft()
                pixels.append((row, col))
                touches_border = touches_border or row == 0 or col == 0 or row == rows - 1 or col == cols - 1
                for row_delta, col_delta in offsets:
                    next_row, next_col = row + row_delta, col + col_delta
                    if (
                        0 <= next_row < rows
                        and 0 <= next_col < cols
                        and not visited[next_row, next_col]
                        and bool(values[next_row, next_col]) == target
                    ):
                        visited[next_row, next_col] = True
                        queue.append((next_row, next_col))
            components.append(PixelComponent(tuple(pixels), touches_border))
    return components


def component_labels(mask, *, connectivity=4):
    """Return a label grid and ordered foreground components."""
    values = np.asarray(mask, dtype=bool)
    components = connected_components(values, connectivity=connectivity)
    labels = np.full(values.shape, -1, dtype=np.int64)
    for component_index, component in enumerate(components):
        rows, cols = zip(*component.pixels)
        labels[np.asarray(rows), np.asarray(cols)] = component_index
    return labels, components
