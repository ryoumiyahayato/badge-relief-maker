import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from badge_relief_maker.app.core.image_transform import ImageTransform
from badge_relief_maker.app.core.project_io import create_project
from badge_relief_maker.app.core.project_model import ExportRecord, ManualMarker
from badge_relief_maker.app.ui.editor_window import MainWindow


def test_editor_window_uses_final_normalized_marker_coordinates():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    geometry = window._marker_geometry("final", 0.25, 0.75, 0.1)

    assert geometry["coordinate_space"] == "final_normalized"
    assert geometry["x"] == 0.25
    assert geometry["y"] == 0.75
    window.close()
    app.processEvents()


def test_final_mask_click_is_persisted_in_source_pixels():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._preview_transform = ImageTransform(
        original_shape=(100, 200),
        crop_box=(20, 10, 180, 90),
        cropped_shape=(80, 160),
        resized_shape=(40, 80),
        geometry_crop_box=(5, 3, 75, 37),
        geometry_shape=(34, 70),
    )

    geometry = window._mask_edit_geometry("final", 0.5, 0.5, 0.1)

    assert geometry["coordinate_space"] == "pixel"
    assert geometry["x"] == pytest.approx(99.5)
    assert geometry["y"] == pytest.approx(49.5)
    assert geometry["radius_px"] == pytest.approx(6.8)
    window.close()
    app.processEvents()


def test_clearing_one_side_preserves_a_both_marker_for_the_other_side():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = create_project("Marker Split")
    window.active_side = "front"
    window.project.manual_markers = [
        ManualMarker(marker_type="height", target="both", data={"x": 0.5, "y": 0.5, "height": 0.7})
    ]

    window._clear_side_coordinate_edits(window.project.front_relief)

    assert len(window.project.manual_markers) == 1
    assert window.project.manual_markers[0].target == "back"
    window.close()
    app.processEvents()


def test_selected_output_folder_receives_unique_copy_and_updates_history(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = create_project("External Export")
    source = tmp_path / "project_assets" / "exports" / "model.stl"
    source.parent.mkdir(parents=True)
    source.write_text("solid sample\nendsolid sample\n", encoding="utf-8")
    report = {"export_path": str(source), "export_format": "stl"}
    window.project.export_history.append(ExportRecord(path=str(source), export_format="stl", report=report))
    selected = tmp_path / "chosen"
    selected.mkdir()
    (selected / "model.stl").write_text("older", encoding="utf-8")
    (selected / "model_2.stl").write_text("also older", encoding="utf-8")
    window.selected_output_directory = str(selected)
    result = SimpleNamespace(output_path=str(source), report=report)

    window._copy_result_to_selected_output(result)

    target = selected / "model_3.stl"
    assert result.output_path == str(target)
    assert target.read_text(encoding="utf-8").startswith("solid sample")
    assert result.report["project_owned_export_path"] == str(source)
    assert window.project.export_history[-1].path == str(target)
    assert window.project.export_history[-1].report is result.report
    window.close()
    app.processEvents()
