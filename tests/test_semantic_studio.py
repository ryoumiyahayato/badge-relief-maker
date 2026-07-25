import os

import pytest

from badge_relief_maker.app.ui.semantic_studio import (
    BRUSH_OPTIONS,
    QUALITY_OPTIONS,
    ROLE_OPTIONS,
    STRENGTH_OPTIONS,
    TOOL_OPTIONS,
)


def test_semantic_editor_contract():
    assert set(ROLE_OPTIONS.values()) == {"background", "solid", "raise", "recess"}
    assert set(TOOL_OPTIONS.values()) == {"part", "brush"}
    assert BRUSH_OPTIONS["小"] < BRUSH_OPTIONS["中"] < BRUSH_OPTIONS["大"]
    assert STRENGTH_OPTIONS["轻微"] < STRENGTH_OPTIONS["标准"] < STRENGTH_OPTIONS["明显"]
    assert QUALITY_OPTIONS["极细模型（约240万网格点）"] == "high"


def test_semantic_studio_constructs_offscreen():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from badge_relief_maker.app.ui.semantic_studio import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.export_button.text() == "确认标注并导出 Blender 模型"
    assert window.phase_two_button.isHidden()
    assert window.region_amount_spin.isHidden()
    assert window.region_radius_spin.isHidden()
    assert window.role_combo.count() == 4
    window.close()
    app.processEvents()
