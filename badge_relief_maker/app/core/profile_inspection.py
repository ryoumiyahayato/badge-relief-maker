"""Physical horizontal and vertical relief cross-section inspection."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


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
    """Sample one field row or column and express both axes in millimeters."""
    values = np.asarray(heightmap, dtype=np.float32)
    footprint = np.asarray(mask, dtype=bool)
    if values.ndim != 2 or values.shape != footprint.shape:
        raise ValueError("heightmap and mask must be matching 2D arrays")
    direction = str(orientation).strip().lower()
    if direction not in {"horizontal", "vertical"}:
        raise ValueError("orientation must be horizontal or vertical")
    position = float(np.clip(position_normalized, 0.0, 1.0))
    rows, cols = values.shape
    if direction == "horizontal":
        index = int(round(position * max(rows - 1, 0)))
        heights = values[index, :] * float(relief_height_mm)
        solid = footprint[index, :]
        coordinates = np.linspace(0.0, float(width_mm), cols, dtype=np.float32)
        physical_position = position * float(height_mm)
        axis_name = "X"
    else:
        index = int(round(position * max(cols - 1, 0)))
        heights = values[:, index] * float(relief_height_mm)
        solid = footprint[:, index]
        coordinates = np.linspace(0.0, float(height_mm), rows, dtype=np.float32)
        physical_position = position * float(width_mm)
        axis_name = "Y"
    samples = heights[solid]
    return {
        "orientation": direction,
        "index": index,
        "position_normalized": position,
        "physical_position_mm": float(physical_position),
        "axis_name": axis_name,
        "coordinates_mm": coordinates,
        "heights_mm": heights,
        "solid": solid,
        "minimum_height_mm": float(samples.min()) if samples.size else 0.0,
        "maximum_height_mm": float(samples.max()) if samples.size else 0.0,
        "mean_height_mm": float(samples.mean()) if samples.size else 0.0,
        "void_fraction": float(np.mean(~solid)) if solid.size else 1.0,
    }


def save_height_profile_preview(profile, path, size=(900, 220)):
    """Render a compact cross-section chart without a plotting dependency."""
    width, height = [max(int(value), 64) for value in size]
    image = Image.new("RGB", (width, height), (20, 23, 28))
    draw = ImageDraw.Draw(image)
    left, right, top, bottom = 54, 20, 20, 36
    plot_width, plot_height = max(width - left - right, 1), max(height - top - bottom, 1)
    coordinates = np.asarray(profile["coordinates_mm"], dtype=np.float32)
    heights = np.asarray(profile["heights_mm"], dtype=np.float32)
    solid = np.asarray(profile["solid"], dtype=bool)
    x_max = max(float(coordinates.max()) if coordinates.size else 0.0, 1e-6)
    y_max = max(float(profile.get("maximum_height_mm", 0.0)), 0.1)
    draw.rectangle((left, top, left + plot_width, top + plot_height), outline=(83, 91, 104))
    for tick in range(5):
        ratio = tick / 4.0
        y = top + plot_height - int(round(ratio * plot_height))
        draw.line((left, y, left + plot_width, y), fill=(45, 51, 61))
        draw.text((left - 7, y), f"{ratio * y_max:.2f}", fill=(180, 188, 200), anchor="rm")
    previous = None
    for coordinate, value, is_solid in zip(coordinates, heights, solid):
        x = left + int(round(float(coordinate) / x_max * plot_width))
        y = top + plot_height - int(round(float(value) / y_max * plot_height))
        if is_solid:
            if previous is not None:
                draw.line((previous[0], previous[1], x, y), fill=(225, 229, 235), width=2)
            previous = (x, y)
        else:
            previous = None
            draw.line((x, top + plot_height - 2, x, top + plot_height), fill=(244, 82, 72))
    header = (
        f"{profile['orientation']} at {profile['physical_position_mm']:.2f} mm | "
        f"min {profile['minimum_height_mm']:.2f} mm | max {profile['maximum_height_mm']:.2f} mm"
    )
    draw.text((left, 4), header, fill=(238, 241, 246))
    draw.text((left, height - 22), "model distance (mm)", fill=(170, 178, 190))
    draw.text((8, top), "Z\nmm", fill=(170, 178, 190))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return str(target)
