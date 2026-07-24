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


def test_emboss_heightmap_preserves_grayscale_order_and_refines_detail():
    rgba = np.full((72, 96, 4), 255, dtype=np.uint8)
    rgba[8:64, 8:88, :3] = (128, 128, 128)
    rgba[18:42, 14:34, :3] = (45, 45, 45)
    rgba[18:42, 62:82, :3] = (220, 220, 220)
    rgba[49:52, 14:82, :3] = (20, 20, 20)
    mask = np.zeros((72, 96), dtype=bool)
    mask[8:64, 8:88] = True

    height = emboss_heightmap(rgba, mask, base_level=0.28, detail_strength=0.72)

    assert height[0, 0] == 0.0
    assert float(height[28, 72]) > float(height[28, 48]) > float(height[28, 24])
    assert float(height[50, 48]) < float(height[44, 48]) - 0.10


def test_new_projects_keep_general_emboss_defaults():
    project = create_project("visual quality")

    assert project.front_relief.height_mode == "emboss"
    assert project.front_relief.quality_mode == "standard"
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


def test_quality_presets_prioritize_source_detail_over_low_end_hardware():
    assert quality_preset("preview")["max_grid_cells"] >= 150_000
    assert quality_preset("standard")["max_grid_cells"] >= 1_000_000
    assert quality_preset("high")["max_grid_cells"] >= 4_000_000
