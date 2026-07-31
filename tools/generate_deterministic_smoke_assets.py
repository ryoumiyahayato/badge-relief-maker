"""Generate deterministic Windows package smoke assets without advanced modules."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image

from badge_relief_maker.app.core.deterministic_workflow import (
    draft_height_master,
    draft_solid_mask,
    export_workflow_artifacts,
    load_source_image,
)


def _write_logo(root: Path):
    image = np.full((96, 128, 3), 255, dtype=np.uint8)
    image[24:72, 34:94] = 0
    source = load_source_image(image)
    solid = draft_solid_mask(source, mode="auto_background", explicit_background="bright", explicit_threshold=0.9)
    height = draft_height_master(source, solid.mask, mode="fixed", fixed_height=0.75)
    return export_workflow_artifacts(
        source,
        solid.mask,
        height.height_master,
        root / "white_background_logo",
        solid_mask_confirmed=True,
        height_master_confirmed=True,
        solid_report=solid.report,
        height_report=height.report,
        source_parameters={"fixture": "white_background_black_logo", "height_mode": "fixed"},
    )


def _write_line_plate(root: Path):
    image = np.full((96, 128), 255, dtype=np.uint8)
    image[30:34, 20:108] = 0
    image[55:59, 20:108] = 0
    source = load_source_image(image)
    solid = draft_solid_mask(source, mode="whole_plate")
    height = draft_height_master(
        source,
        solid.mask,
        mode="line_engrave",
        line_depth_mm=0.2,
        relief_height_mm=3.0,
        line_threshold=0.35,
    )
    return export_workflow_artifacts(
        source,
        solid.mask,
        height.height_master,
        root / "whole_plate_line_engraving",
        solid_mask_confirmed=True,
        height_master_confirmed=True,
        solid_report=solid.report,
        height_report=height.report,
        source_parameters={"fixture": "whole_plate_black_line_engraving", "line_depth_mm": 0.2},
    )


def main(argv=None):
    output = Path((argv or sys.argv[1:])[0] if (argv or sys.argv[1:]) else "smoke-assets").resolve()
    output.mkdir(parents=True, exist_ok=True)
    logo = _write_logo(output)
    line = _write_line_plate(output)
    manifest = {
        "white_background_logo": logo.paths,
        "whole_plate_line_engraving": line.paths,
    }
    (output / "smoke_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    print(output / "smoke_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
