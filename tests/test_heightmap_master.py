import json
from pathlib import Path

import numpy as np
from PIL import Image

from badge_relief_maker.app.core.heightmap_master import export_prepared_heightmap_master
from badge_relief_maker.app.core.relief_parameters import PreparedReliefField


class _Transform:
    pass


def test_heightmap_master_exports_16bit_png_32bit_tiff_and_masks(tmp_path):
    rgba = np.full((48, 32, 4), 255, dtype=np.uint8)
    rgba[4:44, 4:28, :3] = 210
    rgba[18:30, 12:20, :3] = 255
    rgba[:, :, 3] = 255
    mask = np.zeros((48, 32), dtype=bool)
    mask[4:44, 4:28] = True
    height = np.where(mask, 0.35, 0.0).astype(np.float32)
    prepared = PreparedReliefField(mask=mask, heightmap=height, rgba=rgba, image_transform=_Transform(), report={})

    manifest = export_prepared_heightmap_master(prepared, tmp_path, long_edge_px=512)

    png = Image.open(tmp_path / "height_master_16bit.png")
    tiff = Image.open(tmp_path / "height_master_32bit.tiff")
    assert max(png.size) == 512
    assert png.mode in {"I;16", "I"}
    assert tiff.mode == "F"
    assert (tmp_path / "solid_mask.png").is_file()
    assert (tmp_path / "void_mask.png").is_file()
    on_disk = json.loads((tmp_path / "height_master_manifest.json").read_text(encoding="utf-8"))
    assert on_disk["mesh_generation_deferred"] is True
    assert on_disk["bit_depth_png"] == 16
    assert manifest["width_px"] == png.size[0]


def test_project_heightmap_export_is_grayscale_first_and_skips_mesh(tmp_path):
    from badge_relief_maker.app.core.project_build import export_side_heightmap_master_from_project
    from badge_relief_maker.app.core.project_io import create_project, import_image_asset, save_project

    image = np.full((72, 48, 3), 255, dtype=np.uint8)
    image[6:66, 6:42] = 175
    image[20:52, 20:28] = 255
    source = tmp_path / "front.png"
    Image.fromarray(image, mode="RGB").save(source)
    project_path = tmp_path / "sample.medalproj"
    project = create_project("Heightmap first")
    save_project(project, project_path)
    import_image_asset(project, project_path, source, "front")
    save_project(project, project_path)

    result = export_side_heightmap_master_from_project(
        project,
        project_path,
        "front",
        long_edge_px=512,
        output_dir=tmp_path / "heightmaps",
    )

    assert result.vertices.shape == (0, 3)
    assert result.faces.shape == (0, 3)
    assert result.report["mesh_generation_deferred"] is True
    assert Path(result.output_path).is_file()
