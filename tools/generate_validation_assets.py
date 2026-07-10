"""Generate reproducible single-side and fused validation exports.

This script creates local OBJ/STL/GLB files plus independent trimesh read-back
reports. It prepares artifacts for Blender, slicer and CAM review but does not
claim those external applications have been tested.
"""

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from badge_relief_maker.app.core.double_side_builder import build_fused_double_sided_relief
from badge_relief_maker.app.core.export_validation import validate_export
from badge_relief_maker.app.core.manufacturability_check import basic_report
from badge_relief_maker.app.core.mesh_exporter import export_mesh
from badge_relief_maker.app.core.mesh_repair import repair_mesh_basic
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief, prepare_relief_field
from tools.generate_acceptance_fixtures import generate_acceptance_fixtures


FORMATS = ("obj", "stl", "glb")


def _write_formats(directory, stem, vertices, faces, expected_size_mm):
    results = {}
    for export_format in FORMATS:
        path = directory / f"{stem}.{export_format}"
        export_mesh(path, vertices, faces)
        results[export_format] = validate_export(path, expected_size_mm=expected_size_mm)
    return results


def generate_validation_assets(output_directory, max_grid_cells=5000):
    """Generate image fixtures, mesh exports and machine-readable reports."""
    root = Path(output_directory)
    fixture_dir = root / "images"
    export_dir = root / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    fixture_manifest = generate_acceptance_fixtures(fixture_dir)

    single_params = ReliefParameters(
        width_mm=80.0,
        height_mm=60.0,
        base_thickness_mm=2.0,
        relief_height_mm=3.0,
        mask_mode="alpha",
        max_grid_cells=int(max_grid_cells),
        min_component_pixels=1,
        fill_hole_pixels=0,
        mask_smooth_iterations=0,
    )
    single = build_single_side_relief(fixture_dir / "transparent_circle.png", parameters=single_params)
    single_expected = [80.0, 60.0, float(single.report["bbox"]["size_z"])]
    single_exports = _write_formats(export_dir, "single_circle_80x60", single.vertices, single.faces, single_expected)

    ring = build_single_side_relief(fixture_dir / "transparent_ring.png", parameters=single_params)
    ring_path = export_dir / "single_ring_80x60.obj"
    export_mesh(ring_path, ring.vertices, ring.faces)
    ring_validation = validate_export(
        ring_path,
        expected_size_mm=[80.0, 60.0, float(ring.report["bbox"]["size_z"])],
    )

    side_params = ReliefParameters(
        width_mm=80.0,
        height_mm=60.0,
        relief_height_mm=2.0,
        mask_mode="alpha",
        max_grid_cells=int(max_grid_cells),
        min_component_pixels=1,
        fill_hole_pixels=0,
        mask_smooth_iterations=0,
    )
    front = prepare_relief_field(fixture_dir / "asymmetric_front.png", side_params)
    back = prepare_relief_field(fixture_dir / "asymmetric_back.png", side_params)
    fused_vertices, fused_faces, footprint, front_field, back_field, alignment = build_fused_double_sided_relief(
        front.mask,
        front.heightmap,
        back.mask,
        back.heightmap,
        width_mm=80.0,
        height_mm=60.0,
        body_thickness_mm=4.0,
        front_relief_height_mm=2.0,
        back_relief_height_mm=2.0,
        max_grid_cells=int(max_grid_cells),
        alignment={
            "back_scale": 1.0,
            "back_rotation_deg": 0.0,
            "back_offset_x_mm": 0.0,
            "back_offset_y_mm": 0.0,
            "flip_back_horizontal": True,
            "footprint_mode": "intersection",
        },
    )
    fused_vertices, fused_faces, fused_repair = repair_mesh_basic(fused_vertices, fused_faces)
    fused_report = basic_report(
        fused_vertices,
        fused_faces,
        analysis_context={
            "mask": footprint,
            "heightmap": (front_field + back_field) * 0.5,
            "width_mm": 80.0,
            "height_mm": 60.0,
            "base_thickness_mm": 4.0,
            "relief_height_mm": 4.0,
            "construction": "indexed_heightfield",
            "edge_style": "straight",
        },
        process_profile="general",
    )
    fused_expected = [80.0, 60.0, float(fused_report["bbox"]["size_z"])]
    fused_exports = _write_formats(export_dir, "fused_asymmetric_80x60", fused_vertices, fused_faces, fused_expected)

    manifest = {
        "generator": "tools/generate_validation_assets.py",
        "max_grid_cells": int(max_grid_cells),
        "fixture_manifest": fixture_manifest,
        "single_circle": {
            "report": single.report,
            "expected_size_mm": single_expected,
            "exports": single_exports,
        },
        "single_ring": {
            "report": ring.report,
            "export": ring_validation,
        },
        "fused_asymmetric": {
            "alignment": alignment,
            "repair": fused_repair,
            "report": fused_report,
            "expected_size_mm": fused_expected,
            "exports": fused_exports,
        },
        "external_validation": {
            "blender": "pending",
            "slicer": "pending",
            "cam": "pending",
            "physical_sample": "pending",
        },
    }
    (root / "validation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return manifest


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate local mesh validation assets and read-back reports.")
    parser.add_argument("output_directory", nargs="?", default="validation_assets")
    parser.add_argument("--max-grid-cells", type=int, default=5000)
    args = parser.parse_args()
    manifest = generate_validation_assets(args.output_directory, max_grid_cells=args.max_grid_cells)
    export_count = len(manifest["single_circle"]["exports"]) + len(manifest["fused_asymmetric"]["exports"]) + 1
    print(f"Generated {export_count} validation exports in {Path(args.output_directory).resolve()}")


if __name__ == "__main__":
    main()
