from PIL import Image

from badge_relief_maker.app.core.project_io import (
    add_export_record,
    asset_root_for,
    create_project,
    import_image_asset,
    load_project,
    save_project,
)


def test_project_save_load_roundtrip(tmp_path):
    project = create_project("Test Medal")
    project.same_physical_object = False
    project_path = tmp_path / "test.medalproj"

    saved_path = save_project(project, project_path)
    loaded = load_project(saved_path)

    assert loaded.name == "Test Medal"
    assert loaded.same_physical_object is False
    assert asset_root_for(project_path).exists()


def test_import_front_back_and_reference_assets(tmp_path):
    image_path = tmp_path / "source.png"
    Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(image_path)

    project = create_project("Asset Test")
    project_path = tmp_path / "asset_test.medalproj"
    save_project(project, project_path)

    front = import_image_asset(project, project_path, image_path, "front")
    back = import_image_asset(project, project_path, image_path, "back")
    reference = import_image_asset(project, project_path, image_path, "reference", is_reference=True)
    add_export_record(project, "exports/model.obj", "obj", report={"face_count": 1})
    save_project(project, project_path)

    loaded = load_project(project_path)
    assert loaded.front_image.path == front.path
    assert loaded.back_image.path == back.path
    assert loaded.back_relief.enabled is True
    assert len(loaded.reference_images) == 1
    assert loaded.reference_images[0].path == reference.path
    assert loaded.export_history[0].export_format == "obj"
