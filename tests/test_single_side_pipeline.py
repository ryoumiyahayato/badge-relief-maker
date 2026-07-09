import numpy as np
from PIL import Image

from badge_relief_maker.app.core.manufacturability_check import basic_report, edge_usage_report
from badge_relief_maker.app.core.mask_processing import clean_mask, crop_to_mask, resize_mask_and_heightmap
from badge_relief_maker.app.core.masked_solid_builder import build_masked_relief_solid
from badge_relief_maker.app.core.mesh_exporter import export_ascii_stl, export_obj_objects, implemented_formats
from badge_relief_maker.app.core.mesh_optimize import optimize_mesh
from badge_relief_maker.app.core.mesh_repair import repair_mesh_basic
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


def test_masked_relief_solid_returns_stable_empty_arrays():
    heightmap = np.zeros((3, 3), dtype=np.float32)
    mask = np.zeros((3, 3), dtype=bool)
    vertices, faces = build_masked_relief_solid(heightmap, mask, 9.0, 9.0, 1.0, 2.0)
    assert vertices.shape == (0, 3)
    assert faces.shape == (0, 3)
    optimized_vertices, optimized_faces = optimize_mesh(vertices, faces)
    repaired_vertices, repaired_faces, repair_report = repair_mesh_basic(optimized_vertices, optimized_faces)
    assert repaired_vertices.shape == (0, 3)
    assert repaired_faces.shape == (0, 3)
    assert repair_report["invalid_faces_removed"] == 0


def test_masked_relief_solid_closes_internal_height_steps():
    heightmap = np.asarray([[0.25, 1.0]], dtype=np.float32)
    mask = np.asarray([[True, True]], dtype=bool)
    vertices, faces = build_masked_relief_solid(heightmap, mask, 10.0, 5.0, 1.0, 4.0)
    assert len(vertices) > 16
    assert len(faces) > 20


def test_optimize_mesh_deduplicates_vertices():
    vertices = np.asarray([[0, 0, 0], [0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.asarray([[0, 2, 3], [1, 2, 3]], dtype=np.int64)
    new_vertices, new_faces = optimize_mesh(vertices, faces)
    assert len(new_vertices) == 3
    assert len(new_faces) == 2


def test_basic_report_includes_size_and_warnings():
    vertices = np.asarray([[0, 0, -1], [10, 0, 2], [0, 5, 2]], dtype=float)
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)
    report = basic_report(vertices, faces, minimum_thickness_mm=1.0)
    assert report["bbox"]["size_x"] == 10.0
    assert report["bbox"]["size_y"] == 5.0
    assert report["estimated_total_thickness_mm"] == 3.0
    assert report["topology"]["boundary_edge_count"] == 3
    assert "open boundary edges detected" in report["warnings"]


def test_edge_usage_report_detects_closed_tetrahedron():
    faces = np.asarray([[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]], dtype=np.int64)
    report = edge_usage_report(faces)
    assert report["boundary_edge_count"] == 0
    assert report["non_manifold_edge_count"] == 0
    assert report["closed_edge_manifold"] is True


def test_edge_usage_report_detects_non_manifold_edge():
    faces = np.asarray([[0, 1, 2], [1, 0, 3], [0, 1, 4]], dtype=np.int64)
    report = edge_usage_report(faces)
    assert report["non_manifold_edge_count"] == 1
    assert report["closed_edge_manifold"] is False


def test_repair_mesh_basic_removes_invalid_duplicate_and_unused_geometry():
    vertices = np.asarray(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 0],
            [2, 2, 2],
        ],
        dtype=float,
    )
    faces = np.asarray(
        [
            [0, 1, 2],
            [2, 1, 0],
            [0, 0, 3],
            [0, 1, 99],
        ],
        dtype=np.int64,
    )
    new_vertices, new_faces, report = repair_mesh_basic(vertices, faces)
    assert len(new_vertices) == 3
    assert len(new_faces) == 1
    assert report["invalid_faces_removed"] == 1
    assert report["zero_area_faces_removed"] == 1
    assert report["duplicate_faces_removed"] == 1
    assert report["unreferenced_vertices_removed"] == 2


def test_clean_mask_removes_tiny_fragments_and_fills_holes():
    mask = np.zeros((7, 7), dtype=bool)
    mask[1:6, 1:6] = True
    mask[3, 3] = False
    mask[0, 0] = True
    cleaned, report = clean_mask(mask, min_component_pixels=2, fill_hole_pixels=2)
    assert not cleaned[0, 0]
    assert cleaned[3, 3]
    assert report["removed_small_component_pixels"] == 1
    assert report["filled_hole_pixels"] == 1


def test_ascii_stl_export_writes_facets(tmp_path):
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)
    output = tmp_path / "mesh.stl"
    export_ascii_stl(output, vertices, faces)
    text = output.read_text(encoding="utf-8")
    assert text.startswith("solid")
    assert "facet normal" in text
    assert "vertex" in text
    assert "endsolid" in text
    assert {"obj", "stl"}.issubset(implemented_formats())


def test_multi_object_obj_export_writes_named_objects(tmp_path):
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)
    output = tmp_path / "split.obj"
    export_obj_objects(
        output,
        [
            {"name": "front_relief", "vertices": vertices, "faces": faces},
            {"name": "back_relief", "vertices": vertices, "faces": faces},
        ],
    )
    text = output.read_text(encoding="utf-8")
    assert "o front_relief" in text
    assert "o back_relief" in text
    assert "f 1 2 3" in text
    assert "f 4 5 6" in text


def test_crop_to_mask_returns_bbox():
    mask = np.zeros((6, 6), dtype=bool)
    mask[2:4, 2:5] = True
    heightmap = np.ones((6, 6), dtype=np.float32)
    new_mask, new_heightmap, box = crop_to_mask(mask, heightmap, padding=0)
    assert box == (2, 2, 5, 4)
    assert new_mask.shape == (2, 3)
    assert new_heightmap.shape == (2, 3)


def test_resize_mask_and_heightmap_limits_cells():
    mask = np.ones((100, 100), dtype=bool)
    heightmap = np.ones((100, 100), dtype=np.float32)
    new_mask, new_heightmap, scale = resize_mask_and_heightmap(mask, heightmap, max_cells=2500)
    assert new_mask.size <= 2500
    assert new_heightmap.shape == new_mask.shape
    assert scale < 1.0


def test_single_side_pipeline_writes_obj_and_previews(tmp_path):
    image = Image.new("RGBA", (6, 6), (0, 0, 0, 0))
    image.putpixel((2, 2), (255, 255, 255, 255))
    image.putpixel((3, 2), (255, 255, 255, 255))
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
    assert result.report["shape_after_crop"][0] <= result.report["original_shape"][0]
    assert result.report["export_format"] == "obj"
    assert "bbox" in result.report
    assert "warnings" in result.report
    assert "mask_cleanup" in result.report
    assert "mesh_repair" in result.report
    assert "topology" in result.report
    assert (preview_dir / "mask_preview.png").exists()
    assert (preview_dir / "heightmap_preview.png").exists()
    text = output_path.read_text(encoding="utf-8")
    assert "v " in text
    assert "f " in text


def test_single_side_pipeline_handles_empty_foreground(tmp_path):
    image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    image_path = tmp_path / "empty.png"
    output_path = tmp_path / "empty.obj"
    image.save(image_path)

    result = build_single_side_relief(image_path, output_path, ReliefParameters(width_mm=5.0, height_mm=5.0))

    assert output_path.exists()
    assert result.vertices.shape == (0, 3)
    assert result.faces.shape == (0, 3)
    assert result.report["vertex_count"] == 0
    assert result.report["face_count"] == 0
    assert result.report["mask_pixel_count"] == 0
    assert "empty mesh" in result.report["warnings"]
    assert "mask contains no foreground pixels" in result.report["warnings"]


def test_single_side_pipeline_writes_stl(tmp_path):
    image = Image.new("RGBA", (4, 4), (255, 255, 255, 255))
    image_path = tmp_path / "input.png"
    output_path = tmp_path / "output.stl"
    image.save(image_path)

    result = build_single_side_relief(image_path, output_path, ReliefParameters(width_mm=5.0, height_mm=5.0))

    assert output_path.exists()
    assert result.report["export_format"] == "stl"
    text = output_path.read_text(encoding="utf-8")
    assert text.startswith("solid")
    assert "facet normal" in text
