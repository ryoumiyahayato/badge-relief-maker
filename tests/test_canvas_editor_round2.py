import os

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from badge_relief_maker.app.core.deterministic_workflow import (
    background_strength_to_tolerance,
    draft_solid_mask,
    load_source_image,
)
from badge_relief_maker.app.ui.canvas_editor import CanvasEditor
from badge_relief_maker.app.ui.deterministic_studio import MainWindow


def _canvas():
    app = QApplication.instance() or QApplication([])
    canvas = CanvasEditor()
    source = load_source_image(np.full((200, 300, 4), 255, dtype=np.uint8))
    canvas.set_source_data(source)
    canvas.resize(500, 400)
    canvas.show()
    app.processEvents()
    canvas.set_zoom(2.0)
    app.processEvents()
    return app, canvas


def test_background_strength_maps_to_tolerance_and_edge_refinement_is_directional():
    assert background_strength_to_tolerance(0) == pytest.approx(0.0)
    assert background_strength_to_tolerance(100) == pytest.approx(np.sqrt(3.0))
    assert background_strength_to_tolerance(60) > background_strength_to_tolerance(20)

    pixels = np.full((64, 64, 4), 255, dtype=np.uint8)
    pixels[18:46, 18:46, :3] = 0
    image = load_source_image(pixels)
    base = draft_solid_mask(image, mode="auto_background", background_strength=20)
    contracted = draft_solid_mask(image, mode="auto_background", background_strength=20, edge_refinement_px=-2)
    expanded = draft_solid_mask(image, mode="auto_background", background_strength=20, edge_refinement_px=2)

    assert contracted.mask.sum() < base.mask.sum() < expanded.mask.sum()
    assert contracted.report["edge_refinement_effective_px"] == -2
    assert expanded.report["edge_refinement_effective_px"] == 2


@pytest.mark.parametrize("entry", ("middle", "space", "tool"))
def test_all_pan_entries_move_by_scene_delta_without_emitting_strokes(entry):
    app, canvas = _canvas()
    finished = []
    canvas.stroke_finished.connect(finished.append)
    if entry == "tool":
        canvas.set_tool("pan")
    center = canvas.viewport().rect().center()
    before = canvas.viewport_to_image(center)
    if entry == "space":
        QTest.keyPress(canvas, Qt.Key.Key_Space)
    button = Qt.MouseButton.MiddleButton if entry == "middle" else Qt.MouseButton.LeftButton
    QTest.mousePress(canvas.viewport(), button, pos=center)
    QTest.mouseMove(canvas.viewport(), center - QPoint(40, 0))
    QTest.mouseRelease(canvas.viewport(), button, pos=center - QPoint(40, 0))
    if entry == "space":
        QTest.keyRelease(canvas, Qt.Key.Key_Space)
    app.processEvents()
    after = canvas.viewport_to_image(center)
    assert after[0] > before[0]
    assert canvas._panning is False
    assert finished == []
    canvas.close()
    app.processEvents()


def test_screen_brush_radius_scales_with_zoom_and_size_controls_are_immediate():
    app, canvas = _canvas()
    canvas.set_brush_size_px(24)
    canvas.set_zoom(1.0)
    radius_100 = canvas.screen_radius_to_normalized(12)
    canvas.set_zoom(8.0)
    radius_800 = canvas.screen_radius_to_normalized(12)
    assert radius_800 == pytest.approx(radius_100 / 8.0, rel=1e-6)

    finished = []
    canvas.stroke_finished.connect(finished.append)
    point = canvas.normalized_to_viewport((0.5, 0.5)).toPoint()
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert len(finished) == 1
    assert canvas.last_stroke_radius_normalized == pytest.approx(radius_800, rel=1e-6)
    canvas.close()
    app.processEvents()


def test_default_labels_use_direct_actions_and_advanced_height_controls_start_collapsed():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    assert [window.solid_mode_combo.itemText(i) for i in range(window.solid_mode_combo.count())] == ["保留整张图", "去除背景", "手动编辑"]
    assert [window.height_mode_combo.itemText(i) for i in range(window.height_mode_combo.count())] == ["亮处更高", "暗处更高", "刻线", "凸线", "等高"]
    assert window.confirm_solid_button.text() == "确认区域"
    assert window.confirm_height_button.text() == "确认高度"
    assert window.build_button.text() == "生成模型"
    assert window.controls.advanced_group.isChecked() is False
    assert window.controls.background_strength_spin.minimum() == 0
    assert window.controls.background_strength_spin.maximum() == 100
    assert window.controls.edge_refinement_spin.minimum() == -20
    assert window.controls.edge_refinement_spin.maximum() == 20
    window.controls.solid_brush_size_slider.setValue(64)
    app.processEvents()
    assert window.session.solid_brush_size_px == 64
    assert window.canvas.brush_size_px == 64
    window.canvas.setFocus()
    QTest.keyPress(window.canvas, Qt.Key.Key_BracketRight)
    app.processEvents()
    assert window.session.solid_brush_size_px == 69
    assert window.controls.solid_brush_size_spin.value() == 69
    window.close()
    app.processEvents()
