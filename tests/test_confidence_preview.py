from pathlib import Path

import numpy as np
from PIL import Image

from badge_relief_maker.app.core.confidence_preview import (
    build_uncertainty_map,
    save_focused_region_preview,
    save_uncertainty_preview,
)


def _fixture():
    rgba = np.full((64, 80, 4), 255, dtype=np.uint8)
    rgba[15:50, 18:62, :3] = 145
    mask = np.zeros((64, 80), dtype=bool)
    mask[15:50, 18:62] = True
    labels = np.zeros(mask.shape, dtype=np.int32)
    labels[22:42, 28:52] = 1
    report = {
        "regions": [
            {
                "region_id": 1,
                "display_id": 1,
                "pixel_count": 20 * 24,
                "bbox_normalized": [28 / 80, 22 / 64, 52 / 80, 42 / 64],
                "centroid_normalized": [0.5, 0.5],
            }
        ]
    }
    return rgba, mask, labels, report


def test_unresolved_region_increases_uncertainty():
    rgba, mask, labels, report = _fixture()
    uncertainty, metadata = build_uncertainty_map(
        rgba,
        mask,
        lineart_labels=labels,
        lineart_report=report,
        override_report={"applied": []},
    )

    assert uncertainty.shape == mask.shape
    assert float(uncertainty[30, 40]) >= 0.45
    assert metadata["unresolved_region_count"] == 1
    assert 0.0 <= metadata["high_uncertainty_fraction"] <= 1.0


def test_resolved_region_is_less_uncertain_and_previews_save(tmp_path):
    rgba, mask, labels, report = _fixture()
    unresolved, _ = build_uncertainty_map(
        rgba,
        mask,
        lineart_labels=labels,
        lineart_report=report,
        override_report={"applied": []},
    )
    resolved, metadata = build_uncertainty_map(
        rgba,
        mask,
        lineart_labels=labels,
        lineart_report=report,
        override_report={"applied": [{"region_id": 1}]},
    )
    assert float(resolved[30, 40]) < float(unresolved[30, 40])

    heatmap_path = save_uncertainty_preview(rgba, unresolved, tmp_path / "heatmap.png", metadata)
    assert Path(heatmap_path).is_file()

    base = tmp_path / "regions.png"
    Image.fromarray(rgba[:, :, :3], mode="RGB").save(base)
    focused = save_focused_region_preview(base, report["regions"][0], tmp_path / "focused.png")
    assert Path(focused).is_file()
