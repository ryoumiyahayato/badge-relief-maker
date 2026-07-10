import numpy as np

from badge_relief_maker.app.core.mask_generator import foreground_mask


def test_auto_mask_uses_luminance_for_uniform_opaque_images_with_contrast():
    rgba = np.full((5, 5, 4), 255, dtype=np.uint8)
    rgba[2, 2, :3] = 0

    mask, mode = foreground_mask(rgba, mode="auto", luminance_threshold=20)

    assert mode == "luminance"
    assert int(mask.sum()) == 1
    assert mask[2, 2]


def test_auto_mask_preserves_fully_transparent_empty_image():
    rgba = np.zeros((5, 5, 4), dtype=np.uint8)
    rgba[:, :, :3] = 255

    mask, mode = foreground_mask(rgba, mode="auto")

    assert mode == "alpha"
    assert not mask.any()


def test_auto_mask_uses_alpha_when_transparency_is_present():
    rgba = np.full((5, 5, 4), 255, dtype=np.uint8)
    rgba[:, :, 3] = 0
    rgba[1:4, 1:4, 3] = 255

    mask, mode = foreground_mask(rgba, mode="auto")

    assert mode == "alpha"
    assert int(mask.sum()) == 9
