import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from badge_relief_maker.app.core.project_io import create_project
from badge_relief_maker.app.core.project_model import ManualMarker
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
