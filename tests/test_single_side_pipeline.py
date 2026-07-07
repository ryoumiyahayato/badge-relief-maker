import numpy as np
from PIL import Image

from badge_relief_maker.app.core.masked_solid_builder import build_masked_relief_solid
from badge_relief_maker.app.core.mesh_optimize import optimize_mesh
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief
from badge_relief_maker.app.core.solid_builder import build_rectangular_relief_solid


def test_rectangular_relief_solid_has_faces():
    heightmap = np.ones((4, 4), dtype=np.float32)
    vertices, faces = build_rectangular_relief_solid(heightmap, 10.0, 10.0, 1.0, 2.0)
    assert len(vertices) == 32
    assert len(faces) > 0


def test_masked_relief_solid_uses_only_foreground_cells():
    heightmap = np.ones((3, 3), dtype=np.float32)
    mask = np.zeros((3, 3), dtype=bool)
    mask[1, 1] = True
    vertices, faces = build_masked_relief_solid(heightmap, mask, 9.0, 9.0, 1.0, 2.0)
    assert len(vertices) == 8
    assert len(faces) == 12


def test_optimize_mesh_deduplicates_vertices():
    vertices = np.asarray([[0, 0, 0], [0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.asarray([[0, 2, 3], [1, 2, 3]], dtype=np.int64)
    new_vertices, new_faces = optimize_mesh(vertices, faces)
    assert len(new_vertices) == 3
    assert len(new_faces) == 2


def test_single_side_pipeline_writes_obj_and_previews(tmp_path):
    image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    image.putpixel((1, 1), (255, 255, 255, 255))
    image_path = tmp_path / "input.png"
    output_path = tmp_path / "output.obj"
    preview_dir = tmp_path / "previews"
    image.save(image_path)

    params = ReliefParameters(width_mm=10.0, height_mm=10.0, base_thickness_mm=1.0, relief_height_mm=2.0)
    result = build_single_side_relief(image_path, output_path, params, preview_dir=preview_dir)

    assert output_path.exists()
    assert result.report["vertex_count"] > 0
    assert result.report["optimized_vertex_count"] <= result.report["raw_vertex_count"]
    assert result.report["footprint_mode"] == "mask"
    assert (preview_dir / "mask_preview.png").exists()
    assert (preview_dir / "heightmap_preview.png").exists()
    text = output_path.read_text(encoding="utf-8")
    assert "v " in text
    assert "f " in text
