import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from badge_relief_maker.app.core.project_io import create_project
from badge_relief_maker.app.core.quality_modes import QUALITY_PRESETS
from badge_relief_maker.app.ui.main_window import MainWindow
from badge_relief_maker.app.ui.semantic_studio import QUALITY_OPTIONS, REVIEW_OPTIONS, ROLE_OPTIONS


def test_default_gui_exposes_complete_semantic_review_and_adaptive_controls():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.semantic_role_combo.count() == len(ROLE_OPTIONS) == 8
    assert window.review_combo.count() == len(REVIEW_OPTIONS) == 3
    assert window.model_quality_combo.count() == len(QUALITY_OPTIONS) == 3
    assert window.lock_confirmed_check.isChecked()
    assert window.adaptive_mesh_check.isChecked()
    assert window.bezier_editor is not None
    assert window.advanced_tabs.count() == 2
    assert set(QUALITY_OPTIONS.values()) == set(QUALITY_PRESETS)
    for label, mode in QUALITY_OPTIONS.items():
        assert str(QUALITY_PRESETS[mode]["max_grid_cells"] // 10000) in label

    window.close()
    app.processEvents()


def test_dynamic_persisted_controls_mark_dirty_but_project_loading_does_not():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = create_project("Control state")
    window._dirty = False

    window._load_controls_from_project("front")

    assert window._dirty is False
    window.adaptive_mesh_check.setChecked(not window.adaptive_mesh_check.isChecked())
    assert window._dirty is True
    window._dirty = False
    window.close()
    app.processEvents()


def test_bezier_editor_anchor_is_draggable_and_persisted_in_normalized_space():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    editor = window.bezier_editor
    editor.resize(420, 300)
    editor.show()
    editor.new_contour("add")
    app.processEvents()
    before = editor.contours()[0]["points"][0]["anchor"]

    QTest.mousePress(
        editor,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(round(before[0] * editor.width()), round(before[1] * editor.height())),
    )
    QTest.mouseMove(editor, QPoint(250, 90))
    QTest.mouseRelease(
        editor,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(250, 90),
    )
    app.processEvents()

    after = editor.contours()[0]["points"][0]["anchor"]
    assert after == pytest.approx([250 / 420, 90 / 300], abs=0.01)
    assert after != before

    window.close()
    app.processEvents()
