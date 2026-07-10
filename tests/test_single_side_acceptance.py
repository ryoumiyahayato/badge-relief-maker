import numpy as np
import pytest
from PIL import Image

from badge_relief_maker.app.core.heightmap_generator import grayscale_heightmap
from badge_relief_maker.app.core.manufacturability_check import basic_report
from badge_relief_maker.app.core.masked_solid_builder import build_masked_relief_solid
from badge_relief_maker.app.core.quality_modes import quality_preset
from badge_relief_maker.app.core.relief_parameters import ReliefParameters
from badge_relief_maker.app.core.single_side_pipeline import build_single_side_relief


def _assert_closed_outward(vertices, faces, expected_components=1):
    report = basic_report(vertices, faces)
    assert report["topology"]["boundary_edge_count"] == 0
    assert report["topology"]["non_manifold_edge_count"] == 0
    assert report["topology"]["inconsistent_winding_edge_count"] == 0
    assert report["face_geometry"]["invalid_face_count"] == 0
    assert report["face_geometry"]["zero_area_face_count"] == 0
    assert report["components"]["component_count"] == expected_components
    assert report["components"]["closed_oriented_component_count"] == expected_components
    assert report["components"]["inward_closed_component_count"] == 0
    assert all(volume > 0.0 for volume in report["components"]["component_signed_volumes_mm3"])
    return report


def test_uniform_foreground_has_defined_full_height_and_inverts():
    rgba = np.full((3, 4, 4), 128, dtype=np.uint8)
    rgba[:, :, 3] = 255
    mask = np.ones((3, 4), dtype=bool)

    normal = grayscale_heightmap(rgba, mask=mask, invert=False)
    inverted = grayscale_heightmap(rgba, mask=mask, invert=True)

    assert np.all(normal[mask] == 1.0)
    assert np.all(inverted[mask] == 0.0)
    assert np.allclose(inverted[mask], 1.0 - normal[mask])


@pytest.mark.parametrize(
    ("mask", "heightmap", "components"),
    [
        (np.asarray([[True]], dtype=bool), np.asarray([[1.0]], dtype=float), 1),
        (np.ones((3, 5), dtype=bool), np.linspace(0.0, 1.0, 15).reshape(3, 5), 1),
        (
            np.asarray(
                [
                    [False, True, True, True, False],
                    [True, True, True, True, True],
                    [True, True, True, True, True],
                    [True, True, True, True, True],
                    [False, True, True, True, False],
                ],
                dtype=bool,
            ),
            np.ones((5, 5), dtype=float),
            1,
        ),
        (
            np.asarray(
                [
                    [True, True, True, True, True],
                    [True, False, False, False, True],
                    [True, False, False, False, True],
                    [True, True, True, True, True],
                ],
                dtype=bool,
            ),
            np.ones((4, 5), dtype=float),
            1,
        ),
        (np.ones((2, 2), dtype=bool), np.asarray([[0.0, 0.25], [0.75, 1.0]], dtype=float), 1),
        (
            np.asarray([[True, False, False], [False, False, False], [False, False, True]], dtype=bool),
            np.asarray([[0.2, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.8]], dtype=float),
            2,
        ),
        (
            np.asarray([[True, True, False], [True, True, False], [False, False, False]], dtype=bool),
            np.ones((3, 3), dtype=float),
            1,
        ),
    ],
)
def test_masked_builder_acceptance_fixtures(mask, heightmap, components):
    vertices, faces = build_masked_relief_solid(
        heightmap,
        mask,
        width_mm=80.0,
        height_mm=60.0,
        base_thickness_mm=2.0,
        relief_height_mm=3.0,
    )

    report = _assert_closed_outward(vertices, faces, expected_components=components)
    assert report["bbox"]["size_x"] == pytest.approx(80.0)
    assert report["bbox"]["size_y"] == pytest.approx(60.0)


def test_quality_modes_preserve_requested_physical_dimensions(tmp_path):
    image = Image.new("RGBA", (180, 140), (0, 0, 0, 0))
    for y in range(20, 120):
        for x in range(30, 150):
            value = int(255 * (x - 30) / 119)
            image.putpixel((x, y), (value, value, value, 255))
    image_path = tmp_path / "quality-fixture.png"
    image.save(image_path)

    sizes = []
    for mode in ["preview", "standard", "high"]:
        preset = quality_preset(mode)
        result = build_single_side_relief(
            image_path,
            parameters=ReliefParameters(
                width_mm=80.0,
                height_mm=60.0,
                base_thickness_mm=2.0,
                relief_height_mm=3.0,
                max_grid_cells=preset["max_grid_cells"],
                min_component_pixels=preset["min_component_pixels"],
                fill_hole_pixels=preset["fill_hole_pixels"],
                mask_smooth_iterations=preset["mask_smooth_iterations"],
            ),
        )
        sizes.append((result.report["bbox"]["size_x"], result.report["bbox"]["size_y"]))
        assert result.report["dimension_error_mm"]["x"] <= 0.05
        assert result.report["dimension_error_mm"]["y"] <= 0.05
        assert result.report["manufacturing_gate"]["topology_checks_passed"] is True

    assert sizes == pytest.approx([(80.0, 60.0), (80.0, 60.0), (80.0, 60.0)])
