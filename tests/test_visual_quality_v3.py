from pathlib import Path

import numpy as np
from PIL import Image

from badge_relief_maker.app.core.heightmap_generator import emboss_heightmap
from badge_relief_maker.app.core.mask_generator import foreground_mask
from badge_relief_maker.app.core.project_io import create_project
from badge_relief_maker.app.core.quality_modes import quality_preset
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import prepare_relief_field


def test_auto_mask_keeps_enclosed_light_artwork_inside_badge_silhouette():
    rgba = np.full((80, 80, 4), 255, dtype=np.uint8)
    rgba[10:70, 10:70, :3] = (50, 110, 210)
    rgba[20:60, 20:60, :3] = 255
    rgba[34:46, 34:46, :3] = 0

    mask, mode = foreground_mask(rgba, mode="auto", luminance_threshold=20)

    assert mode == "background"
    assert not mask[0, 0]
    assert mask[12, 12]
    assert mask[25, 25]  # enclosed white artwork remains part of the solid
    assert mask[40, 40]


def test_emboss_heightmap_uses_stable_plateau_and_raises_local_detail():
    rgba = np.full((64, 64, 4), 255, dtype=np.uint8)
    rgba[8:56, 8:56, :3] = (120, 120, 120)
    rgba[30:34, 14:50, :3] = 0
    mask = np.zeros((64, 64), dtype=bool)
    mask[8:56, 8:56] = True

    height = emboss_heightmap(rgba, mask, base_level=0.28, detail_strength=0.72)

    assert height[0, 0] == 0.0
    assert 0.25 <= float(height[20, 20]) <= 0.40
    assert float(height[30, 30]) > float(height[20, 20]) + 0.20


def test_new_projects_default_to_emboss_instead_of_raw_brightness_depth():
    project = create_project("visual quality")

    assert project.front_relief.height_mode == "emboss"
    assert project.front_relief.uniform_height_normalized == 0.28


def test_pipeline_writes_shaded_relief_preview(tmp_path):
    rgba = np.zeros((48, 48, 4), dtype=np.uint8)
    rgba[5:43, 5:43] = (130, 130, 130, 255)
    rgba[22:26, 10:38] = (0, 0, 0, 255)
    image_path = tmp_path / "badge.png"
    Image.fromarray(rgba, mode="RGBA").save(image_path)

    prepared = prepare_relief_field(
        image_path,
        ReliefParameters(mask_mode="alpha", height_mode="emboss", uniform_height_normalized=0.28),
        preview_dir=tmp_path / "previews",
    )

    relief_preview = Path(prepared.report["preview_paths"]["relief_preview"])
    assert relief_preview.is_file()
    assert Image.open(relief_preview).mode == "RGB"


def test_quality_presets_no_longer_hide_badge_detail_at_tiny_grids():
    assert quality_preset("preview")["max_grid_cells"] >= 20_000
    assert quality_preset("standard")["max_grid_cells"] >= 80_000
    assert quality_preset("high")["max_grid_cells"] >= 250_000
