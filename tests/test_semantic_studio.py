import os

import pytest

from badge_relief_maker.app.ui.semantic_studio import (
    BRUSH_OPTIONS,
    QUALITY_OPTIONS,
    REVIEW_OPTIONS,
    ROLE_OPTIONS,
    STRENGTH_OPTIONS,
    TOOL_OPTIONS,
)


def test_semantic_editor_contract():
    semantic_roles = {item["semantic_role"] for item in ROLE_OPTIONS.values()}
    assert semantic_roles == {
        "background",
        "level_base",
        "level_low",
        "level_mid",
        "level_high",
        "level_top",
        "raise",
        "recess",
    }
    assert set(TOOL_OPTIONS.values()) == {"part", "brush"}
    assert set(REVIEW_OPTIONS.values()) == {"regions", "uncertainty", "mask"}
    assert BRUSH_OPTIONS["小"] < BRUSH_OPTIONS["中"] < BRUSH_OPTIONS["大"]
    assert STRENGTH_OPTIONS["轻微"] < STRENGTH_OPTIONS["标准"] < STRENGTH_OPTIONS["明显"]
    assert QUALITY_OPTIONS["极细模型（约480万网格点）"] == "high"
    levels = [
        ROLE_OPTIONS["实体补填／底面"]["height"],
        ROLE_OPTIONS["低层浮雕"]["height"],
        ROLE_OPTIONS["中层浮雕"]["height"],
        ROLE_OPTIONS["高层浮雕"]["height"],
        ROLE_OPTIONS["最高构件"]["height"],
    ]
    assert levels == sorted(levels)


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
    assert window.role_combo.count() == 8
    assert window.lock_check.isChecked()
    assert window.review_combo.count() == 3
    assert window.section_preview is not None
    window.close()
    app.processEvents()
