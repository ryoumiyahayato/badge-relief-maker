import numpy as np

from badge_relief_maker.app.core.heightmap_generator import emboss_heightmap
from badge_relief_maker.app.core.lineart_region_graph import (
    analyze_lineart_regions,
    apply_lineart_region_overrides,
)


def _fixture():
    rgba = np.full((80, 100, 4), 255, dtype=np.uint8)
    mask = np.zeros((80, 100), dtype=bool)
    mask[5:75, 5:95] = True
    # Two enclosed light regions separated by dark boundaries. One represents a
    # surface panel, the other an ambiguous hole/shadow.
    rgba[20:23, 15:85, :3] = 0
    rgba[57:60, 15:85, :3] = 0
    rgba[20:60, 15:18, :3] = 0
    rgba[20:60, 82:85, :3] = 0
    rgba[35:38, 20:80, :3] = 0
    return rgba, mask


def test_lineart_region_report_marks_closed_light_regions_unresolved():
    rgba, mask = _fixture()
    _, report = analyze_lineart_regions(rgba, mask)

    assert report["requires_region_confirmation"] is True
    assert report["unresolved_region_count"] >= 2
    assert "never auto-raise" in report["default_policy"]


def test_region_background_override_removes_selected_region_from_solid():
    rgba, mask = _fixture()
    height = emboss_heightmap(rgba, mask, base_level=0.28, detail_strength=0.72)

    new_mask, new_height, report = apply_lineart_region_overrides(
        rgba,
        mask,
        height,
        [{"x": 0.50, "y": 0.48, "coordinate_space": "final_normalized", "role": "background"}],
    )

    assert report["applied_override_count"] == 1
    assert not new_mask[38, 50]
    assert new_height[38, 50] == 0.0


def test_region_surface_override_matches_surrounding_level_instead_of_raising():
    rgba, mask = _fixture()
    height = emboss_heightmap(rgba, mask, base_level=0.28, detail_strength=0.72)
    height[23:35, 18:82] += 0.2

    new_mask, new_height, report = apply_lineart_region_overrides(
        rgba,
        mask,
        height,
        [{"x": 0.50, "y": 0.30, "coordinate_space": "final_normalized", "role": "surface"}],
    )

    assert report["applied_override_count"] == 1
    assert new_mask[28, 50]
    assert abs(float(new_height[28, 50]) - float(new_height[19, 50])) < 0.12
