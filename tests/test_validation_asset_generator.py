import json

from tools.generate_validation_assets import generate_validation_assets


def test_validation_asset_generator_writes_reloadable_single_and_fused_exports(tmp_path):
    manifest = generate_validation_assets(tmp_path, max_grid_cells=240)

    for section in ("single_circle", "fused_asymmetric"):
        assert set(manifest[section]["exports"]) == {"obj", "stl", "glb"}
        for export_format, report in manifest[section]["exports"].items():
            assert (tmp_path / "exports" / ("single_circle_80x60" if section == "single_circle" else "fused_asymmetric_80x60")).with_suffix(
                f".{export_format}"
            ).is_file()
            assert report["watertight"] is True
            assert report["winding_consistent"] is True
            assert report["positive_volume"] is True
            assert report["dimensions_match"] is True

    assert manifest["single_ring"]["export"]["watertight"] is True
    assert manifest["fused_asymmetric"]["report"]["components"]["component_count"] == 1
    assert manifest["external_validation"]["blender"] == "pending"

    stored = json.loads((tmp_path / "validation_manifest.json").read_text(encoding="utf-8"))
    assert stored["max_grid_cells"] == 240
    assert stored["external_validation"]["physical_sample"] == "pending"
