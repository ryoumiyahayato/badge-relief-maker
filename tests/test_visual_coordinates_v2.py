import pytest

from badge_relief_maker.app.core.image_transform import ImageTransform
from badge_relief_maker.app.core.marker_transform import transform_manual_height_markers


def _final_transform():
    return ImageTransform(
        original_shape=(100, 200),
        crop_box=(20, 10, 180, 90),
        cropped_shape=(80, 160),
        resized_shape=(40, 80),
        geometry_crop_box=(5, 3, 75, 37),
        geometry_shape=(34, 70),
    )


def test_final_grid_point_round_trips_to_source_coordinates():
    transform = _final_transform()
    target = transform.original_to_target_point(0.5, 0.5, normalized=True)
    source = transform.target_to_original_point(*target)

    assert target == pytest.approx((34.5, 16.5))
    assert source == pytest.approx((99.5, 49.5))


def test_final_normalized_height_marker_uses_exact_target_grid():
    transform = _final_transform()
    marker = {
        "marker_type": "height",
        "target": "front",
        "shape": "circle",
        "x": 0.5,
        "y": 0.5,
        "radius_normalized": 0.1,
        "coordinate_space": "final_normalized",
        "height_normalized": 0.75,
    }

    transformed = transform_manual_height_markers(marker, image_transform=transform)

    assert len(transformed) == 1
    assert transformed[0]["coordinate_space"] == "pixel"
    assert transformed[0]["x"] == pytest.approx(34.5)
    assert transformed[0]["y"] == pytest.approx(16.5)
    assert transformed[0]["radius_px"] == pytest.approx(3.4)


def test_processed_normalized_marker_is_shifted_by_geometry_crop():
    transform = _final_transform()
    marker = {
        "marker_type": "height",
        "target": "front",
        "x": 0.5,
        "y": 0.5,
        "radius_normalized": 0.1,
        "coordinate_space": "processed_normalized",
        "height_normalized": 0.5,
    }

    transformed = transform_manual_height_markers(marker, image_transform=transform)

    assert len(transformed) == 1
    assert transformed[0]["x"] == pytest.approx(34.5)
    assert transformed[0]["y"] == pytest.approx(16.5)
    assert transformed[0]["radius_px"] == pytest.approx(4.0)


def test_final_brush_radius_can_be_persisted_in_source_pixels():
    transform = _final_transform()

    source_radius = transform.target_radius_to_original(0.1, normalized=True)
    round_trip = transform.original_radius_to_processed(source_radius)

    assert source_radius == pytest.approx(6.8)
    assert round_trip == pytest.approx(3.4)
