import numpy as np
import pytest

from badge_relief_maker.app.core.height_markers import apply_manual_height_markers


def test_smooth_brush_spreads_a_peak_inside_foreground():
    heightmap = np.zeros((5, 5), dtype=float)
    heightmap[2, 2] = 1.0
    mask = np.ones((5, 5), dtype=bool)

    result, report = apply_manual_height_markers(
        heightmap,
        mask,
        {
            "marker_type": "height",
            "operation": "smooth",
            "value": 1.0,
            "x": 0.5,
            "y": 0.5,
            "radius_px": 2.0,
        },
    )

    assert report["applied_marker_count"] == 1
    assert result[2, 2] == pytest.approx(1.0 / 9.0)
    assert result[2, 1] == pytest.approx(1.0 / 9.0)
    assert result[0, 0] == 0.0


def test_smooth_brush_does_not_average_background_holes_into_foreground():
    heightmap = np.ones((5, 5), dtype=float)
    mask = np.ones((5, 5), dtype=bool)
    mask[2, 2] = False
    heightmap[~mask] = 0.0

    result, report = apply_manual_height_markers(
        heightmap,
        mask,
        {
            "marker_type": "height",
            "operation": "smooth",
            "strength": 1.0,
            "x": 0.5,
            "y": 0.5,
            "radius_px": 2.0,
        },
    )

    assert report["applied_marker_count"] == 1
    assert result[2, 1] == pytest.approx(1.0)
    assert result[1, 2] == pytest.approx(1.0)
    assert result[2, 2] == 0.0


def test_smooth_brush_preserves_foreground_boundary_plateau():
    heightmap = np.zeros((5, 5), dtype=float)
    mask = np.zeros((5, 5), dtype=bool)
    mask[1:4, 1:4] = True
    heightmap[mask] = 0.75

    result, _ = apply_manual_height_markers(
        heightmap,
        mask,
        {
            "marker_type": "height",
            "operation": "blur",
            "value": 1.0,
            "x": 0.5,
            "y": 0.5,
            "radius_px": 3.0,
        },
    )

    assert np.allclose(result[mask], 0.75)
    assert np.all(result[~mask] == 0.0)
