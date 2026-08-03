import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QScrollArea

from badge_relief_maker.app.ui.canvas_editor import CanvasEditor
from badge_relief_maker.app.ui.deterministic_studio import APP_TITLE, MainWindow
from badge_relief_maker.app.ui.editor_session import CanvasTool, EditorMode


def test_default_window_is_canvas_first_with_three_modes_and_one_main_canvas():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.windowTitle() == APP_TITLE
    assert isinstance(window.canvas, CanvasEditor)
    assert window.canvas.objectName() == "canvasEditor"
    assert window.controls.property_stack.count() == 3
    assert set(window.controls.tool_buttons) == {item.value for item in CanvasTool}
    assert set(mode.value for mode in EditorMode) == {"solid", "height", "mesh"}
    window.show()
    app.processEvents()
    assert window.controls.confirm_solid_button.isVisible()
    assert not window.controls.confirm_height_button.isVisible()
    assert not window.controls.build_button.isVisible()
    assert not window.log_box.isVisible()
    assert window.detail_button.isVisible()
    assert any(area.widgetResizable() for area in window.findChildren(QScrollArea))
    for width, height in ((1366, 768), (1400, 900)):
        window.resize(width, height)
        app.processEvents()
        assert window.canvas.width() >= width * 0.60 - 20
        assert window.controls.build_button.geometry().height() > 0
        assert window.log_box.geometry().height() > 0
    window.close()
    app.processEvents()
