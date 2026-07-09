import numpy as np

from badge_relief_maker.app.core.rim_builder import apply_outer_rim_to_heightmap, rim_boost_map, rim_distance_map


def test_smooth_rim_profile_is_softer_than_linear_midway():
    mask = np.ones((5, 5), dtype=bool)
    distances = rim_distance_map(mask, width_px=3)
    linear = rim_boost_map(mask, width_px=3, boost_normalized=0.6, profile="linear")
    smooth = rim_boost_map(mask, width_px=3, boost_normalized=0.6, profile="smooth")

    assert int(distances[0, 0]) == 0
    assert int(distances[1, 1]) == 1
    assert int(distances[2, 2]) == 2
    assert float(smooth[0, 0]) == 0.6
    assert float(smooth[1, 1]) > float(linear[1, 1])
    assert float(smooth[2, 2]) < float(linear[2, 2])


def test_apply_outer_rim_to_heightmap_supports_smooth_profile():
    heightmap = np.zeros((5, 5), dtype=np.float32)
    mask = np.ones((5, 5), dtype=bool)
    boosted, report = apply_outer_rim_to_heightmap(
        heightmap,
        mask,
        width_px=3,
        rim_height_mm=1.2,
        relief_height_mm=2.0,
        profile="smooth",
    )

    assert report["enabled"] is True
    assert report["rim_profile"] == "smooth"
    assert report["rim_pixel_count"] == 25
    assert float(boosted[0, 0]) == 0.6
    assert float(boosted[1, 1]) > 0.4
    assert float(boosted[2, 2]) < 0.2
