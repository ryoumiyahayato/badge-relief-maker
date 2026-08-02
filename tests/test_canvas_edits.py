import numpy as np

from badge_relief_maker.app.core.canvas_edits import (
    apply_canvas_solid_edits,
    interpolate_points,
    normalized_edit_record,
    replay_height_edits,
    stroke_roi,
)


def test_stroke_interpolation_keeps_spacing_below_quarter_radius():
    radius = 0.08
    points = interpolate_points([[0.1, 0.2], [0.9, 0.8]], radius * 0.25)
    distances = np.linalg.norm(np.diff(np.asarray(points), axis=0), axis=1)
    assert len(points) > 2
    assert float(distances.max()) <= radius * 0.25 + 1e-9


def test_solid_stroke_add_and_erase_are_continuous_and_have_roi():
    mask = np.zeros((64, 64), dtype=bool)
    add = normalized_edit_record("add", [[0.1, 0.5], [0.9, 0.5]], 0.04)
    mask = apply_canvas_solid_edits(mask, [add])
    assert mask.sum() > 64
    roi = stroke_roi(mask.shape, add["points"], add["radius_normalized"])
    assert roi == (27, 37, 2, 62)

    erase = normalized_edit_record("remove", [[0.45, 0.5], [0.55, 0.5]], 0.04)
    erased = apply_canvas_solid_edits(mask, [erase])
    assert erased.sum() < mask.sum()


def test_height_strokes_set_raise_lower_and_smooth_inside_mask_only():
    mask = np.ones((48, 48), dtype=bool)
    mask[:4, :] = False
    height = np.full(mask.shape, 0.5, dtype=np.float32)
    height[~mask] = 0.0
    edits = [
        normalized_edit_record("set", [[0.2, 0.5], [0.8, 0.5]], 0.06, value=0.75),
        normalized_edit_record("add", [[0.3, 0.5], [0.7, 0.5]], 0.04, amount=0.1),
        normalized_edit_record("subtract", [[0.4, 0.5], [0.6, 0.5]], 0.03, amount=0.2),
        normalized_edit_record("smooth", [[0.45, 0.5], [0.55, 0.5]], 0.04, amount=0.25),
    ]
    result = replay_height_edits(height, mask, edits)
    assert result.min() >= 0.0
    assert result.max() <= 1.0
    assert np.all(result[~mask] == 0.0)
    assert np.any(result[mask] > 0.5)


def test_edit_record_is_normalized_and_round_trippable():
    record = normalized_edit_record("add", [[0.2, 0.3], [0.8, 0.7]], 0.0125)
    assert record["shape"] == "stroke"
    assert record["coordinate_space"] == "normalized"
    assert record["radius_normalized"] == 0.0125
    assert record["points"][0] == [0.2, 0.3]
    assert record["points"][-1] == [0.8, 0.7]
