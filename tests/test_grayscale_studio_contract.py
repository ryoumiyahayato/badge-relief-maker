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


def test_grayscale_studio_constructs_offscreen():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from badge_relief_maker.app.ui.grayscale_studio import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
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
