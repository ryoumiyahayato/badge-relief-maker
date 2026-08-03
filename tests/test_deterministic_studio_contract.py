import os

import pytest

from badge_relief_maker.app.ui.deterministic_studio import (
    APP_SUBTITLE,
    APP_TITLE,
    HEIGHT_MODE_OPTIONS,
    QUALITY_OPTIONS,
    SOLID_MODE_OPTIONS,
)


def test_default_studio_exposes_three_explicit_product_decisions():
    assert "确定性" in APP_TITLE
    assert "区域" in APP_SUBTITLE
    assert SOLID_MODE_OPTIONS == {
        "保留整张图": "whole_plate",
        "去除背景": "auto_background",
        "手动编辑": "custom",
    }
    assert HEIGHT_MODE_OPTIONS == {
        "亮处更高": "bright_high",
        "暗处更高": "dark_high",
        "刻线": "line_engrave",
        "凸线": "line_emboss",
        "等高": "fixed",
    }
    assert QUALITY_OPTIONS == {"快速": "draft", "标准": "standard", "精细": "fine"}


def test_default_studio_constructs_with_four_previews_and_visible_build_controls():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QScrollArea
    from PySide6.QtTest import QTest

    from badge_relief_maker.app.ui.deterministic_studio import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.windowTitle() == APP_TITLE
    assert window.source_preview is not None
    assert window.solid_preview is not None
    assert window.height_preview is not None
    assert window.mesh_preview is not None
    assert window.confirm_solid_button.text() == "确认区域"
    assert window.confirm_height_button.text() == "确认高度"
    assert window.build_button.text() == "生成模型"

    for width, height in ((1366, 768), (1400, 900)):
        window.resize(width, height)
        window.show()
        app.processEvents()
        assert window.confirm_solid_button.isVisible()
        assert not window.confirm_height_button.isVisible()
        assert not window.build_button.isVisible()
        assert not window.log_box.isVisible()
        assert window.confirm_solid_button.geometry().height() > 0
        assert window.confirm_solid_button.geometry().height() > 0
        assert window.log_box.geometry().height() > 0
        scroll_areas = window.findChildren(QScrollArea)
        assert scroll_areas
        assert any(area.isVisible() and area.widgetResizable() for area in scroll_areas)

    window.close()
    app.processEvents()


def test_default_studio_persists_confirmed_truth_and_mesh_controls(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import numpy as np
    from PIL import Image
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from badge_relief_maker.app.ui.deterministic_studio import MainWindow

    app = QApplication.instance() or QApplication([])
    image_path = tmp_path / "source.png"
    image = np.tile(np.linspace(0, 255, 48, dtype=np.uint8), (32, 1))
    Image.fromarray(image).save(image_path)

    window = MainWindow()
    window.load_image(image_path)
    window.solid_mode_combo.setCurrentText("保留整张图")
    window.confirm_solid()
    window.refresh_height()
    for _ in range(100):
        app.processEvents()
        QTest.qWait(5)
        if window.height_draft is not None:
            break
    window.height_mode_combo.setCurrentText("等高")
    window.fixed_height_spin.setValue(0.65)
    window.width_spin.setValue(123.0)
    window.height_spin.setValue(77.0)
    window.base_spin.setValue(2.4)
    window.relief_spin.setValue(3.6)
    window.min_feature_spin.setValue(0.25)
    window.quality_combo.setCurrentText("精细")
    window.format_combo.setCurrentText("STL")
    window.confirm_height()

    project_path = window.artifact_directory / "project.json"
    assert project_path.is_file()
    original_mask = window.solid_draft.mask.copy()
    original_height = window.height_draft.height_master.copy()

    reopened = MainWindow()
    reopened.load_project(project_path)
    assert reopened.solid_mask_confirmed is True
    assert reopened.height_master_confirmed is True
    assert np.array_equal(reopened.solid_draft.mask, original_mask)
    assert np.allclose(reopened.height_draft.height_master, original_height, atol=1.0 / 65535.0)
    assert reopened.width_spin.value() == 123.0
    assert reopened.height_spin.value() == 77.0
    assert reopened.base_spin.value() == 2.4
    assert reopened.relief_spin.value() == 3.6
    assert reopened.min_feature_spin.value() == 0.25
    assert reopened.quality_combo.currentText() == "精细"
    assert reopened.format_combo.currentText() == "STL"
    reopened.close()
    window.close()
    app.processEvents()
