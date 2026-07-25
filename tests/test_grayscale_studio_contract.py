import os

import pytest

from badge_relief_maker.app.ui.grayscale_studio import (
    APP_SUBTITLE,
    APP_TITLE,
    QUALITY_OPTIONS,
    REGION_OPERATIONS,
)


def test_grayscale_studio_is_chinese_first_and_phase_one_focused():
    assert APP_TITLE == "勋章灰度图生成器"
    assert "单张图片" in APP_SUBTITLE
    assert "灰度高度图" in APP_SUBTITLE


def test_grayscale_studio_exposes_high_resolution_master_options():
    assert QUALITY_OPTIONS["标准（4096 像素）"] == 4096
    assert QUALITY_OPTIONS["高精（8192 像素）"] == 8192
    assert QUALITY_OPTIONS["极致（12288 像素）"] == 12288


def test_region_edits_are_reduced_to_four_explicit_roles():
    assert REGION_OPERATIONS["挖空／设为背景"] == "background"
    assert REGION_OPERATIONS["设为承载面"] == "surface"
    assert REGION_OPERATIONS["抬高为前景构件"] == "raise"
    assert REGION_OPERATIONS["压低为凹陷／阴影"] == "recess"


def _qt_window():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from badge_relief_maker.app.ui.grayscale_studio import MainWindow

    app = QApplication.instance() or QApplication([])
    return app, MainWindow()


def test_grayscale_studio_constructs_offscreen():
    app, window = _qt_window()
    assert window.windowTitle() == APP_TITLE
    assert window.import_button.text() == "1  导入图片"
    assert window.generate_button.text() == "2  生成／刷新灰度图"
    assert window.export_button.text() == "3  导出高精度灰度图"
    assert window.phase_two_button.isEnabled() is False
    assert window.source_preview is not None
    assert window.region_preview is not None
    assert window.height_preview is not None
    window.close()
    app.processEvents()


def test_photo_background_click_creates_source_space_mask_brush(monkeypatch):
    from badge_relief_maker.app.core.project_io import create_project

    class _Transform:
        @staticmethod
        def target_to_original_point(x, y, normalized=True):
            assert normalized is True
            return x * 1000.0, y * 800.0

        @staticmethod
        def target_radius_to_original(radius, normalized=True):
            assert normalized is True
            return radius * 600.0

    app, window = _qt_window()
    window.project = create_project("photo")
    window._artwork_interpretation = "continuous_tone"
    window._preview_transform = _Transform()
    window.region_operation_combo.setCurrentText("挖空／设为背景")
    monkeypatch.setattr(window, "_save_project", lambda: None)
    monkeypatch.setattr(window, "generate_previews", lambda: None)

    window.apply_region_operation(0.5, 0.4)

    edit = window.project.front_relief.mask_edits[-1]
    assert edit["operation"] == "remove"
    assert edit["coordinate_space"] == "pixel"
    assert edit["x"] == 500.0
    assert edit["y"] == 320.0
    assert edit["radius_px"] > 0.0
    window.close()
    app.processEvents()


def test_lineart_click_preserves_whole_region_override(monkeypatch):
    from badge_relief_maker.app.core.project_io import create_project

    app, window = _qt_window()
    window.project = create_project("lineart")
    window._artwork_interpretation = "lineart"
    window.region_operation_combo.setCurrentText("抬高为前景构件")
    monkeypatch.setattr(window, "_save_project", lambda: None)
    monkeypatch.setattr(window, "generate_previews", lambda: None)

    window.apply_region_operation(0.25, 0.75)

    override = window.project.front_relief.lineart_region_overrides[-1]
    assert override["role"] == "raise"
    assert override["coordinate_space"] == "final_normalized"
    window.close()
    app.processEvents()
