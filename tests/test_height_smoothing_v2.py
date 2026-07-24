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


def test_rounded_region_layer_keeps_boundary_near_carrier_and_raises_interior():
    from badge_relief_maker.app.core.height_processing import apply_region_layers

    mask = np.ones((81, 81), dtype=bool)
    height = np.full((81, 81), 0.25, dtype=np.float32)
    layers = [
        {
            "shape": "ellipse",
            "x": 0.5,
            "y": 0.5,
            "width_normalized": 0.7,
            "height_size_normalized": 0.5,
            "height_normalized": 0.85,
            "profile": "rounded",
            "detail_mix": 0.0,
        }
    ]

    result, _, report = apply_region_layers(height, mask, layers)

    assert report["rounded_layer_count"] == 1
    assert result[40, 40] > 0.80
    assert result[40, 12] < 0.35
