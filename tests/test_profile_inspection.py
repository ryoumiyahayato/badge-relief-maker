from pathlib import Path

import numpy as np

from badge_relief_maker.app.core.profile_inspection import sample_height_profile, save_height_profile_preview


def test_horizontal_and_vertical_profiles_use_physical_units(tmp_path):
    heightmap = np.tile(np.linspace(0.0, 1.0, 12, dtype=np.float32), (8, 1))
    mask = np.ones(heightmap.shape, dtype=bool)
    mask[:, :2] = False

    horizontal = sample_height_profile(
        heightmap,
        mask,
        orientation="horizontal",
        position_normalized=0.5,
        width_mm=60.0,
        height_mm=40.0,
        relief_height_mm=3.0,
    )
    vertical = sample_height_profile(
        heightmap,
        mask,
        orientation="vertical",
        position_normalized=1.0,
        width_mm=60.0,
        height_mm=40.0,
        relief_height_mm=3.0,
    )

    assert horizontal["physical_position_mm"] == 20.0
    assert horizontal["maximum_height_mm"] == 3.0
    assert horizontal["void_fraction"] > 0.0
    assert vertical["physical_position_mm"] == 60.0
    assert vertical["maximum_height_mm"] == 3.0

    output = save_height_profile_preview(horizontal, tmp_path / "profile.png")
    assert Path(output).is_file()
