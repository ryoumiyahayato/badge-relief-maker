import json
import os

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from badge_relief_maker.app.ui.deterministic_studio import MainWindow


def test_stroke_records_approval_state_and_formal_artifacts_survive_reopen(tmp_path):
    app = QApplication.instance() or QApplication([])
    image_path = tmp_path / "badge.png"
    image = np.full((40, 56), 255, dtype=np.uint8)
    image[10:30, 18:38] = 0
    Image.fromarray(image).save(image_path)

    window = MainWindow()
    window.load_image(image_path)
    window.solid_mode_combo.setCurrentIndex(0)
    window.set_tool("brush_add")
    window._on_stroke_finished([[0.2, 0.2], [0.8, 0.2]])
    solid_record = list(window.solid_edits)
    assert solid_record[0]["shape"] == "stroke"
    assert window.confirm_solid()
    window._compute_height_preview_sync()
    window.height_mode_combo.setCurrentIndex(4)
    window.fixed_height_spin.setValue(0.65)
    window.set_tool("height_set")
    window._on_stroke_finished([[0.3, 0.5], [0.7, 0.5]])
    assert window.confirm_height()
    project_path = window.artifact_directory / "project.json"
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    assert payload["editor_schema_version"] == 2
    assert payload["solid_mask_edits"] == solid_record
    assert payload["height_edits"][0]["shape"] == "stroke"

    reopened = MainWindow()
    reopened.load_project(project_path)
    assert reopened.solid_mask_confirmed is True
    assert reopened.height_master_confirmed is True
    assert reopened.solid_edits == window.solid_edits
    assert reopened.height_edits == window.height_edits
    assert np.array_equal(reopened.session.formal_solid_mask, window.session.formal_solid_mask)
    assert np.allclose(reopened.session.formal_height_master, window.session.formal_height_master, atol=1.0 / 65535.0)
    reopened.close()
    window.close()
    app.processEvents()
