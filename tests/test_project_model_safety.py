from badge_relief_maker.app.core.project_model import MedalProject


def test_project_model_filters_non_string_image_identity_fields():
    project = MedalProject.from_dict(
        {
            "name": "Record Safety",
            "front_image": {"role": "front", "path": ["not", "a", "path"]},
            "back_image": {"role": ["back"], "path": "assets/back.png"},
            "reference_images": [
                {"role": "reference", "path": "assets/reference.png", "preprocessing": "bad"},
                {"role": "", "path": "assets/empty-role.png"},
                {"role": "reference", "path": ""},
            ],
        }
    )

    assert project.front_image is None
    assert project.back_image is None
    assert len(project.reference_images) == 1
    assert project.reference_images[0].path == "assets/reference.png"
    assert project.reference_images[0].preprocessing == {}


def test_project_model_filters_empty_marker_and_export_identity_fields():
    project = MedalProject.from_dict(
        {
            "name": "Record Safety",
            "manual_markers": [
                {"marker_type": "height", "target": "front", "data": {}},
                {"marker_type": "", "target": "front", "data": {}},
                {"marker_type": "height", "target": ["front"], "data": {}},
            ],
            "export_history": [
                {"path": "exports/model.obj", "export_format": "OBJ", "report": "bad"},
                {"path": "", "export_format": "obj"},
                {"path": "exports/model.stl", "export_format": ["stl"]},
            ],
        }
    )

    assert len(project.manual_markers) == 1
    assert project.manual_markers[0].marker_type == "height"
    assert project.manual_markers[0].target == "front"
    assert len(project.export_history) == 1
    assert project.export_history[0].path == "exports/model.obj"
    assert project.export_history[0].export_format == "obj"
    assert project.export_history[0].report == {}


def test_project_model_normalizes_invalid_name_and_saved_booleans():
    project = MedalProject.from_dict(
        {
            "name": ["not", "text"],
            "same_physical_object": "false",
            "edge": {"rim_enabled": "false", "use_smoothed_side_walls": "true"},
            "front_relief": {"enabled": "true", "invert_height": "false", "crop_to_foreground": "true"},
        }
    )

    assert project.name == "Untitled"
    assert project.same_physical_object is False
    assert project.edge.rim_enabled is False
    assert project.edge.use_smoothed_side_walls is True
    assert project.front_relief.enabled is True
    assert project.front_relief.invert_height is False
    assert project.front_relief.crop_to_foreground is True
