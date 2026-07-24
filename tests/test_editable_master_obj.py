from pathlib import Path

import numpy as np
from PIL import Image

from badge_relief_maker.app.core.mesh_exporter import (
    export_obj_face_groups,
    single_side_surface_face_groups,
)
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief


def _simple_closed_single_side_mesh():
    vertices = np.asarray(
        [
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.2],
            [1.0, 1.0, 1.1],
            [0.0, 1.0, 1.0],
            [0.0, 0.0, -2.0],
            [1.0, 0.0, -2.0],
            [1.0, 1.0, -2.0],
            [0.0, 1.0, -2.0],
        ],
        dtype=float,
    )
    faces = np.asarray(
        [
            [0, 1, 2], [0, 2, 3],
            [4, 6, 5], [4, 7, 6],
            [0, 4, 5], [0, 5, 1],
            [1, 5, 6], [1, 6, 2],
            [2, 6, 7], [2, 7, 3],
            [3, 7, 4], [3, 4, 0],
        ],
        dtype=np.int64,
    )
    return vertices, faces


def test_single_side_groups_cover_complete_mesh_without_overlap():
    vertices, faces = _simple_closed_single_side_mesh()
    groups = single_side_surface_face_groups(vertices, faces)

    assert set(groups) == {"front_relief", "side_wall", "flat_back"}
    combined = np.concatenate(list(groups.values()))
    assert sorted(combined.tolist()) == list(range(len(faces)))
    assert len(groups["front_relief"]) == 2
    assert len(groups["flat_back"]) == 2
    assert len(groups["side_wall"]) == 8


def test_editable_obj_keeps_one_object_and_named_shared_vertex_face_groups(tmp_path):
    vertices, faces = _simple_closed_single_side_mesh()
    groups = single_side_surface_face_groups(vertices, faces)
    output = tmp_path / "master.obj"

    export_obj_face_groups(output, vertices, faces, groups, object_name="complete_medal")
    text = output.read_text(encoding="utf-8")

    assert "o complete_medal\n" in text
    assert "g front_relief\n" in text
    assert "g side_wall\n" in text
    assert "g flat_back\n" in text
    assert sum(line.startswith("v ") for line in text.splitlines()) == len(vertices)
    assert sum(line.startswith("f ") for line in text.splitlines()) == len(faces)


def test_pipeline_obj_is_closed_editable_master_with_automatic_flat_back(tmp_path):
    rgba = np.zeros((28, 28, 4), dtype=np.uint8)
    rgba[4:24, 4:24] = (150, 150, 150, 255)
    rgba[11:17, 8:20] = (35, 35, 35, 255)
    image_path = tmp_path / "badge.png"
    Image.fromarray(rgba, mode="RGBA").save(image_path)
    output = tmp_path / "badge_master.obj"

    result = build_single_side_relief(
        image_path,
        output,
        ReliefParameters(
            mask_mode="alpha",
            height_mode="emboss",
            width_mm=40.0,
            height_mm=40.0,
            base_thickness_mm=2.0,
            relief_height_mm=3.0,
            max_grid_cells=100_000,
        ),
    )

    assert Path(result.output_path).is_file()
    assert result.report["editable_master"] is True
    assert result.report["back_surface_mode"] == "flat_plane"
    assert result.report["assembly_mode"] == "single_relief_closed_solid_with_flat_back"
    assert set(result.report["editable_surface_groups"]) == {"front_relief", "side_wall", "flat_back"}
    assert result.report["topology"]["boundary_edge_count"] == 0
    assert result.report["topology"]["non_manifold_edge_count"] == 0
    assert np.ptp(result.vertices[np.isclose(result.vertices[:, 2], result.vertices[:, 2].min()), 2]) == 0.0
    text = output.read_text(encoding="utf-8")
    assert "g front_relief\n" in text
    assert "g side_wall\n" in text
    assert "g flat_back\n" in text
