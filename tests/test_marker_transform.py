from badge_relief_maker.app.core.marker_transform import transform_manual_height_markers


def test_processed_marker_coordinates_remain_pixel_coordinates():
    marker = {
        "marker_type": "height",
        "x": 4,
        "y": 3,
        "radius_px": 2,
        "height_normalized": 0.5,
        "coordinate_space": "processed",
    }

    transformed = transform_manual_height_markers(
        marker,
        original_shape=(100, 100),
        crop_box=(10, 20, 90, 80),
        cropped_shape=(60, 80),
        resized_shape=(30, 40),
    )

    assert len(transformed) == 1
    assert transformed[0]["coordinate_space"] == "pixel"
    assert transformed[0]["x"] == 4
    assert transformed[0]["y"] == 3
    assert transformed[0]["radius_px"] == 2
