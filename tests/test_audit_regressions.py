import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from badge_relief_maker.app.core.heightmap_generator import grayscale_heightmap
from badge_relief_maker.app.core.manufacturability_check import edge_usage_report, mesh_bounds
from badge_relief_maker.app.core.marker_transform import transform_manual_height_markers
from badge_relief_maker.app.core.masked_solid_builder import build_masked_relief_solid
from badge_relief_maker.app.core.mesh_optimize import optimize_mesh
from badge_relief_maker.app.core.mesh_repair import repair_mesh_basic
from badge_relief_maker.app.core.project_build import _mirror_z_mesh, build_front_relief_from_project_file
from badge_relief_maker.app.core.project_io import create_project, import_image_asset, resolve_project_asset, save_project
from badge_relief_maker.app.core.project_model import MedalProject
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief


def _signed_volume(vertices, faces):
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=np.int64)
    triangles = vertices[faces]
    return float(np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum() / 6.0)


def _directed_edge_counts(faces):
    directed = Counter()
    undirected = Counter()
    for a, b, c in np.asarray(faces, dtype=np.int64):
        for start, end in [(a, b), (b, c), (c, a)]:
            directed[(int(start), int(end))] += 1
            undirected[tuple(sorted((int(start), int(end))))] += 1
    return directed, undirected


def test_package_module_entrypoint_runs_from_repository_root():
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root)

    completed = subprocess.run(
        [sys.executable, "-m", "badge_relief_maker.app"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Badge Relief Maker" in completed.stdout


def test_non_uniform_two_cell_height_field_is_closed_and_consistently_wound():
    heightmap = np.asarray([[0.25, 1.0]], dtype=float)
    mask = np.ones_like(heightmap, dtype=bool)

    vertices, faces = build_masked_relief_solid(heightmap, mask, 80.0, 40.0, 2.0, 3.0)
    vertices, faces = optimize_mesh(vertices, faces)
    vertices, faces, _ = repair_mesh_basic(vertices, faces)
    topology = edge_usage_report(faces)
    directed, undirected = _directed_edge_counts(faces)

    assert topology["boundary_edge_count"] == 0
    assert topology["non_manifold_edge_count"] == 0
    assert topology["closed_edge_manifold"] is True
    assert all(count == 2 for count in undirected.values())
    assert all(directed[(a, b)] == directed[(b, a)] == 1 for a, b in undirected)
    assert _signed_volume(vertices, faces) > 0.0


def test_mask_padding_does_not_change_requested_final_dimensions():
    heightmap = np.ones((6, 6), dtype=float)
    mask = np.zeros((6, 6), dtype=bool)
    mask[1:5, 1:5] = True

    vertices, faces = build_masked_relief_solid(heightmap, mask, 80.0, 80.0, 2.0, 3.0)
    bounds = mesh_bounds(vertices)

    assert len(faces) > 0
    assert np.isclose(bounds["size_x"], 80.0)
    assert np.isclose(bounds["size_y"], 80.0)


def test_opaque_jpg_uses_luminance_mask_in_auto_mode(tmp_path):
    pixels = np.full((10, 10, 3), 255, dtype=np.uint8)
    pixels[3:7, 3:7] = 0
    image_path = tmp_path / "opaque.jpg"
    Image.fromarray(pixels, mode="RGB").save(image_path, quality=100, subsampling=0)

    result = build_single_side_relief(
        image_path,
        parameters=ReliefParameters(width_mm=80.0, height_mm=80.0, mask_mode="auto", crop_padding_px=1),
    )

    assert result.report["mask_mode_used"] == "luminance"
    assert result.report["mask_pixel_count"] < 100
    assert np.isclose(result.report["bbox"]["size_x"], 80.0)
    assert np.isclose(result.report["bbox"]["size_y"], 80.0)


def test_heightmap_normalization_uses_only_masked_pixels():
    rgba = np.asarray([[[0, 0, 0, 0], [100, 100, 100, 255], [200, 200, 200, 255]]], dtype=np.uint8)
    mask = np.asarray([[False, True, True]])

    heightmap = grayscale_heightmap(rgba, mask=mask)

    assert float(heightmap[0, 0]) == 0.0
    assert float(heightmap[0, 1]) == 0.0
    assert float(heightmap[0, 2]) == 1.0


def test_reference_role_cannot_escape_images_directory_and_imports_do_not_overwrite(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(source)
    project_path = tmp_path / "safe.medalproj"
    project = create_project("Safe Assets")
    save_project(project, project_path)

    first = import_image_asset(project, project_path, source, "../../escaped", is_reference=True)
    second = import_image_asset(project, project_path, source, "../../escaped", is_reference=True)
    first_path = resolve_project_asset(project_path, first.path)
    second_path = resolve_project_asset(project_path, second.path)
    images_dir = (tmp_path / "safe_assets" / "images").resolve()

    assert first.role == "escaped"
    assert first_path.parent == images_dir
    assert second_path.parent == images_dir
    assert first_path != second_path
    assert first_path.exists() and second_path.exists()


def test_z_mirror_reverses_winding_and_preserves_signed_volume():
    vertices, faces = build_masked_relief_solid(np.ones((1, 1)), np.ones((1, 1), dtype=bool), 10.0, 10.0, 2.0, 3.0)
    original_volume = _signed_volume(vertices, faces)

    mirrored_vertices, mirrored_faces = _mirror_z_mesh(vertices, faces)
    mirrored_volume = _signed_volume(mirrored_vertices, mirrored_faces)

    assert original_volume > 0.0
    assert np.isclose(mirrored_volume, original_volume)


def test_original_pixel_marker_is_transformed_through_crop_and_resize():
    markers = ({"marker_type": "height", "x": 5, "y": 3, "coordinate_space": "pixel", "radius_px": 1, "height": 0.5},)

    transformed = transform_manual_height_markers(
        markers,
        original_shape=(10, 10),
        crop_box=(4, 2, 8, 6),
        cropped_shape=(4, 4),
        resized_shape=(2, 2),
    )

    assert len(transformed) == 1
    assert transformed[0]["coordinate_space"] == "pixel"
    assert np.isclose(transformed[0]["x"], 1.0 / 3.0)
    assert np.isclose(transformed[0]["y"], 1.0 / 3.0)
    assert np.isclose(transformed[0]["radius_px"], 0.5)


def test_project_exports_use_distinct_paths(tmp_path):
    image_path = tmp_path / "front.png"
    Image.new("RGBA", (6, 6), (255, 255, 255, 255)).save(image_path)
    project_path = tmp_path / "history.medalproj"
    project = create_project("History")
    save_project(project, project_path)
    import_image_asset(project, project_path, image_path, "front")
    save_project(project, project_path)

    first = build_front_relief_from_project_file(project_path, export_format="obj", quality_mode="preview")
    second = build_front_relief_from_project_file(project_path, export_format="obj", quality_mode="preview")

    assert first.output_path != second.output_path
    assert Path(first.output_path).exists()
    assert Path(second.output_path).exists()


def test_project_string_booleans_are_parsed_explicitly():
    project = MedalProject.from_dict(
        {
            "name": "Boolean Test",
            "same_physical_object": "false",
            "edge": {"rim_enabled": "false", "use_smoothed_side_walls": "obsolete"},
            "back_relief": {"enabled": "false"},
        }
    )

    assert project.same_physical_object is False
    assert project.edge.rim_enabled is False
    assert not hasattr(project.edge, "use_smoothed_side_walls")
    assert project.back_relief.enabled is False
