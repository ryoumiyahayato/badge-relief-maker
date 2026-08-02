import os

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from badge_relief_maker.app.ui.canvas_editor import CanvasEditor
from badge_relief_maker.app.core.deterministic_workflow import load_source_image


def _canvas():
    app = QApplication.instance() or QApplication([])
    canvas = CanvasEditor()
    source = load_source_image(np.full((100, 160, 4), 255, dtype=np.uint8))
    canvas.set_source_data(source)
    canvas.resize(800, 500)
    canvas.show()
    app.processEvents()
    return app, canvas


def test_normalized_coordinates_survive_zoom_and_pan():
    app, canvas = _canvas()
    normalized = (0.37, 0.62)
    viewport = canvas.normalized_to_viewport(normalized)
    assert viewport is not None
    before = canvas.image_to_normalized(canvas.viewport_to_image(viewport))
    canvas._apply_zoom(2.0)
    after_zoom = canvas.image_to_normalized(canvas.viewport_to_image(canvas.normalized_to_viewport(normalized)))
    assert before == pytest.approx(normalized, abs=1e-6)
    assert after_zoom == pytest.approx(normalized, abs=1e-6)
    assert canvas.viewport_to_image(QPoint(-20, -20)) is None
    canvas.close()
    app.processEvents()


def test_one_mouse_drag_emits_one_complete_stroke_with_intermediate_points():
    app, canvas = _canvas()
    finished = []
    canvas.stroke_finished.connect(finished.append)
    start = canvas.normalized_to_viewport((0.15, 0.5))
    end = canvas.normalized_to_viewport((0.85, 0.5))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start.toPoint())
    for fraction in np.linspace(0.2, 0.8, 4):
        point = QPoint(round(start.x() + (end.x() - start.x()) * float(fraction)), round(start.y() + (end.y() - start.y()) * float(fraction)))
        QTest.mouseMove(canvas.viewport(), point)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end.toPoint())
    app.processEvents()
    assert len(finished) == 1
    assert len(finished[0]) > 4
    canvas.close()
    app.processEvents()
