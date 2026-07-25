"""Cross-section sampling and compact preview rendering for relief review."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


_SUPPORTED_ORIENTATIONS = {"horizontal", "vertical"}


def sample_height_profile(
    heightmap,
    mask,
    *,
    orientation="horizontal",
    position_normalized=0.5,
    width_mm=80.0,
    height_mm=80.0,
    relief_height_mm=3.0,
):
    """Sample one row or column and return physical coordinates and heights."""
    values = np.asarray(heightmap, dtype=np.float32)
    footprint = np.asarray(mask, dtype=bool)
    if values.ndim != 2 or values.shape != footprint.shape:
        raise ValueError("heightmap and mask must be matching 2D arrays")
    orientation = str(orientation).strip().lower()
    if orientation not in _SUPPORTED_ORIENTATIONS:
        raise ValueError("orientation must be horizontal or vertical")
    position = float(np.clip(position_normalized, 0.0, 1.0))
    rows, cols = values.shape

    if orientation == "horizontal":
        index = int(round(position * max(rows - 1, 0)))
        heights = values[index, :].astype(np.float32) * float(relief_height_mm)
        solid = footprint[index, :]
        coordinates = np.linspace(0.0, float(width_mm), cols, dtype=np.float32)
        physical_position = position * float(height_mm)
        axis_name = "X"
    else:
        index = int(round(position * max(cols - 1, 0)))
        heights = values[:, index].astype(np.float32) * float(relief_height_mm)
        solid = footprint[:, index]
        coordinates = np.linspace(0.0, float(height_mm), rows, dtype=np.float32)
        physical_position = position * float(width_mm)
        axis_name = "Y"

    solid_heights = heights[solid]
    return {
        "orientation": orientation,
        "index": index,
        "position_normalized": position,
        "physical_position_mm": float(physical_position),
        "axis_name": axis_name,
        "coordinates_mm": coordinates,
        "heights_mm": heights,
        "solid": solid,
        "minimum_height_mm": float(solid_heights.min()) if solid_heights.size else 0.0,
        "maximum_height_mm": float(solid_heights.max()) if solid_heights.size else 0.0,
        "mean_height_mm": float(solid_heights.mean()) if solid_heights.size else 0.0,
        "void_fraction": float(np.mean(~solid)) if solid.size else 1.0,
    }


def save_height_profile_preview(profile, path, size=(900, 220)):
    """Render a dark, readable cross-section chart without external plotting tools."""
    width, height = [max(int(value), 64) for value in size]
    image = Image.new("RGB", (width, height), (20, 23, 28))
    draw = ImageDraw.Draw(image)
    margin_left = 54
    margin_right = 20
    margin_top = 20
    margin_bottom = 36
    plot_width = max(width - margin_left - margin_right, 1)
    plot_height = max(height - margin_top - margin_bottom, 1)

    coordinates = np.asarray(profile["coordinates_mm"], dtype=np.float32)
    heights = np.asarray(profile["heights_mm"], dtype=np.float32)
    solid = np.asarray(profile["solid"], dtype=bool)
    x_max = max(float(coordinates.max()) if coordinates.size else 0.0, 1e-6)
    y_max = max(float(profile.get("maximum_height_mm", 0.0)), 0.1)

    draw.rectangle(
        (margin_left, margin_top, margin_left + plot_width, margin_top + plot_height),
        outline=(83, 91, 104),
    )
    for tick in range(5):
        ratio = tick / 4.0
        y = margin_top + plot_height - int(round(ratio * plot_height))
        draw.line((margin_left, y, margin_left + plot_width, y), fill=(45, 51, 61))
        draw.text((margin_left - 7, y), f"{ratio * y_max:.2f}", fill=(180, 188, 200), anchor="rm")

    previous = None
    for coordinate, value, is_solid in zip(coordinates, heights, solid):
        x = margin_left + int(round(float(coordinate) / x_max * plot_width))
        y = margin_top + plot_height - int(round(float(value) / y_max * plot_height))
        if is_solid:
            if previous is not None:
                draw.line((previous[0], previous[1], x, y), fill=(225, 229, 235), width=2)
            previous = (x, y)
        else:
            previous = None
            draw.line((x, margin_top + plot_height - 2, x, margin_top + plot_height), fill=(244, 82, 72))

    position = float(profile.get("physical_position_mm", 0.0))
    orientation_text = "水平" if profile.get("orientation") == "horizontal" else "垂直"
    header = (
        f"{orientation_text}截面　位置 {position:.2f} mm　"
        f"最低 {profile.get('minimum_height_mm', 0.0):.2f} mm　"
        f"最高 {profile.get('maximum_height_mm', 0.0):.2f} mm"
    )
    draw.text((margin_left, 4), header, fill=(238, 241, 246))
    draw.text((margin_left, height - 22), "横轴：模型尺寸（mm）", fill=(170, 178, 190))
    draw.text((8, margin_top), "高度\nmm", fill=(170, 178, 190))

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return str(output)
