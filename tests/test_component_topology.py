import numpy as np
from PIL import Image

from badge_relief_maker.app.core.manufacturability_check import basic_report
from badge_relief_maker.app.core.masked_solid_builder import build_masked_relief_solid
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief


def test_diagonally_touching_components_remain_separate_closed_solids():
    heightmap = np.asarray([[1.0, 0.0], [0.0, 0.5]], dtype=float)
    mask = np.asarray([[True, False], [False, True]], dtype=bool)

    vertices, faces = build_masked_relief_solid(heightmap, mask, 20.0, 20.0, 2.0, 3.0)
    report = basic_report(vertices, faces)

    assert report["topology"]["boundary_edge_count"] == 0
    assert report["topology"]["non_manifold_edge_count"] == 0
    assert report["topology"]["inconsistent_winding_edge_count"] == 0
    assert report["topology"]["closed_oriented_manifold"] is True
    assert report["face_geometry"]["signed_volume_mm3"] > 0.0


def test_pipeline_preserves_component_vertex_namespaces(tmp_path):
    image = Image.new("RGBA", (3, 3), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 255, 255, 255))
    image.putpixel((1, 1), (128, 128, 128, 255))
    image_path = tmp_path / "diagonal-components.png"
    image.save(image_path)

    result = build_single_side_relief(
        image_path,
        parameters=ReliefParameters(
            width_mm=20.0,
            height_mm=20.0,
            base_thickness_mm=2.0,
            relief_height_mm=3.0,
            crop_padding_px=0,
        ),
    )

    assert result.report["mesh_optimization"]["mode"] == "indexed_builder_preserved"
    assert result.report["mesh_optimization"]["global_vertex_deduplication"] is False
    assert result.report["topology"]["boundary_edge_count"] == 0
    assert result.report["topology"]["non_manifold_edge_count"] == 0
    assert result.report["topology"]["closed_oriented_manifold"] is True
