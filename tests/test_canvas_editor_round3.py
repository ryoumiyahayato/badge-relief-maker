import os

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from badge_relief_maker.app.core.deterministic_workflow import export_grayscale_heightmaps
from badge_relief_maker.app.ui.deterministic_studio import MainWindow
from badge_relief_maker.app.ui.editor_session import EditorMode


def _window(tmp_path):
    app = QApplication.instance() or QApplication([])
    image_path = tmp_path / "badge.png"
    image = np.full((40, 56), 190, dtype=np.uint8)
    image[10:30, 16:40] = 40
    Image.fromarray(image).save(image_path)
    window = MainWindow()
    window.load_image(image_path)
    window._compute_solid_preview_sync()
    return app, window


def test_stage_tools_follow_confirmation_state(tmp_path):
    app, window = _window(tmp_path)
    window.show()
    window.set_mode(EditorMode.SOLID)
    app.processEvents()
    assert window.controls.solid_manual_group.isVisible()
    assert window.controls.tool_buttons["brush_add"].isVisible()
    assert not window.controls.tool_buttons["height_set"].isVisible()

    assert window.confirm_solid()
    app.processEvents()
    assert window.session.editor_mode == EditorMode.HEIGHT
    assert not window.controls.tool_buttons["height_set"].isVisible()
    assert window.controls.height_edit_hint.text() == "请先生成高度图"

    window._compute_height_preview_sync()
    window._update_state()
    app.processEvents()
    assert window.controls.tool_buttons["height_set"].isVisible()
    assert window.controls.tool_buttons["height_smooth"].isVisible()
    assert window.canvas._items["height"].isVisible()
    assert window.canvas.height_display_mode == "grayscale"
    assert not window.set_mode(EditorMode.MESH)
    assert window.controls.mesh_mode_button.toolTip() == "请先确认高度"
    window.close()
    app.processEvents()


def test_grayscale_layer_is_single_channel_and_outside_is_zero(tmp_path):
    app, window = _window(tmp_path)
    assert window.confirm_solid()
    window._compute_height_preview_sync()
    window.session.editor_mode = EditorMode.HEIGHT
    window._render_canvas_layers()
    window._update_state()
    image = window.canvas._items["height"].pixmap().toImage()
    pixel = image.pixelColor(0, 0)
    assert pixel.red() == pixel.green() == pixel.blue()
    window.close()
    app.processEvents()


def test_grayscale_export_writes_formal_master_preview_and_float_tiff(tmp_path):
    mask = np.zeros((8, 10), dtype=bool)
    mask[2:6, 3:8] = True
    height = np.zeros(mask.shape, dtype=np.float32)
    height[mask] = np.linspace(0.0, 1.0, int(mask.sum()), dtype=np.float32)
    paths = export_grayscale_heightmaps(height, mask, tmp_path)
    assert set(paths) == {"height_master_16bit", "height_master_preview", "height_master_32bit"}
    assert all((tmp_path / name).is_file() for name in ("height_master_16bit.png", "height_master_preview.png", "height_master_32bit.tiff"))
    with Image.open(paths["height_master_16bit"]) as image:
        assert np.asarray(image).dtype == np.uint16
    with Image.open(paths["height_master_preview"]) as image:
        assert np.asarray(image).dtype == np.uint8
    with Image.open(paths["height_master_32bit"]) as image:
        assert np.asarray(image).dtype == np.float32


def test_detail_log_is_collapsed_and_deduplicates_identical_user_errors(tmp_path):
    app, window = _window(tmp_path)
    window.show()
    app.processEvents()
    assert not window.log_box.isVisible()
    window._show_user_error("请先确认区域，再编辑高度。", {"reason": "locked"})
    first = window.log_box.toPlainText()
    window._show_user_error("请先确认区域，再编辑高度。", {"reason": "locked"})
    assert window.log_box.toPlainText() == first
    window.detail_button.click()
    app.processEvents()
    assert window.log_box.isVisible()
    assert '"reason": "locked"' in window.log_box.toPlainText()
    window.close()
    app.processEvents()
