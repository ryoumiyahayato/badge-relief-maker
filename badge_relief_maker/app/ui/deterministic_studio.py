"""Default canvas-first deterministic relief editor."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QProgressBar,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover - core-only installations
    Qt = None
    QApplication = QFileDialog = QHBoxLayout = QLabel = QProgressBar = QPushButton = QTextEdit = QVBoxLayout = None
    QMainWindow = object
    QWidget = object

from ..core.approved_heightmap_builder import build_relief_from_approved_heightmap
from ..core.canvas_edits import normalized_edit_record, replay_height_edits
from ..core.deterministic_workflow import (
    HEIGHT_MODES,
    SOLID_MODES,
    HeightMasterDraft,
    SolidMaskDraft,
    background_strength_to_tolerance,
    draft_height_master,
    draft_solid_mask,
    export_workflow_artifacts,
    export_grayscale_heightmaps,
    load_source_image,
    load_workflow_artifacts,
)
from ..core.quality_modes import quality_preset
from ..core.relief_parameters import ReliefParameters
from .background_jobs import CancellationToken, DebouncedJob, JobController, JobError, JobResult
from .canvas_editor import CanvasEditor
from .editor_controls import EditorControls
from .editor_session import CanvasTool, EditorMode, EditorSession


APP_TITLE = "确定性灰度浮雕直接编辑器"
APP_SUBTITLE = "区域 → 高度 → 模型；确认后模型只读取正式主图"
SOLID_MODE_OPTIONS = {
    "保留整张图": "whole_plate",
    "去除背景": "auto_background",
    "手动编辑": "custom",
}
HEIGHT_MODE_OPTIONS = {
    "亮处更高": "bright_high",
    "暗处更高": "dark_high",
    "刻线": "line_engrave",
    "凸线": "line_emboss",
    "等高": "fixed",
}
QUALITY_OPTIONS = {"快速": "draft", "标准": "standard", "精细": "fine"}

TOOL_LABELS = {
    CanvasTool.BACKGROUND_SAMPLE: "取背景色",
    CanvasTool.BRUSH_ADD: "添加区域",
    CanvasTool.BRUSH_ERASE: "擦除区域",
    CanvasTool.FILL: "填充区域",
    CanvasTool.RECTANGLE: "矩形",
    CanvasTool.POLYGON: "多边形",
    CanvasTool.HEIGHT_SET: "设置高度",
    CanvasTool.HEIGHT_RAISE: "抬高",
    CanvasTool.HEIGHT_LOWER: "降低",
    CanvasTool.HEIGHT_SMOOTH: "平滑",
}


def _preview_data(source_data, maximum_edge: int = 1536):
    """Create an editor copy without changing the original source snapshot."""
    rows, cols = source_data.rgba8.shape[:2]
    if max(rows, cols) <= maximum_edge:
        return source_data
    scale = float(maximum_edge) / max(rows, cols)
    size = (max(1, round(cols * scale)), max(1, round(rows * scale)))
    image = Image.fromarray(source_data.rgba8, mode="RGBA").resize(size, Image.Resampling.LANCZOS)
    return load_source_image(np.asarray(image))


def _resize_layer(array, shape, *, mask=False):
    values = np.asarray(array)
    rows, cols = int(shape[0]), int(shape[1])
    if values.shape[:2] == (rows, cols):
        return values.copy()
    image = Image.fromarray((values.astype(np.uint8) * 255) if mask else values.astype(np.float32), mode="L" if mask else "F")
    resized = image.resize((cols, rows), Image.Resampling.NEAREST if mask else Image.Resampling.BILINEAR)
    result = np.asarray(resized)
    if mask:
        return result >= 128
    return result.astype(np.float32)


class MainWindow(QMainWindow):
    """Window assembly and workflow coordinator for the direct editor."""

    def __init__(self):
        super().__init__()
        try:
            from .qt_text import install_readable_ui_font

            install_readable_ui_font(QApplication.instance())
        except Exception:
            pass
        self.session = EditorSession()
        self.editor_session = self.session
        self.source_path: Path | None = None
        self.mesh_result = None
        self._solid_job_request = None
        self._height_job_request = None
        self._mesh_job_request = None
        self._detail_log_entries: list[str] = []
        self._last_status_key = None
        self._last_error_key = None
        self._pending_region_selection = None
        self._loading_controls = False
        self._build_ui()
        self._connect_signals()
        self.job_controller = JobController(self)
        self.job_controller.job_started.connect(self._job_started)
        self.job_controller.succeeded.connect(self._job_succeeded)
        self.job_controller.failed.connect(self._job_failed)
        self.job_controller.progress.connect(self._job_progress)
        self.job_controller.finished.connect(self._job_finished)
        self.solid_debouncer = DebouncedJob(lambda _payload: self.refresh_solid(), self, 200)
        self.height_debouncer = DebouncedJob(lambda _payload: self.refresh_height(auto=True), self, 200)
        self._sync_aliases()
        self._update_state()

    # ------------------------------------------------------------------ setup
    def _build_ui(self):
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1100, 700)
        self.resize(1400, 900)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.controls = EditorControls(self)
        root.addWidget(self.controls.top_bar)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.controls.tool_bar, 0)
        self.canvas = CanvasEditor(self)
        self.canvas.setMinimumWidth(680)
        body.addWidget(self.canvas, 1)
        body.addWidget(self.controls.property_scroll, 0)
        root.addLayout(body, 1)

        task_bar = QWidget()
        task_layout = QHBoxLayout(task_bar)
        task_layout.setContentsMargins(8, 4, 8, 4)
        self.task_name_label = QLabel("就绪")
        self.task_name_label.setMinimumWidth(150)
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 100)
        self.task_progress.setValue(0)
        self.task_progress.setTextVisible(False)
        self.cancel_task_button = QPushButton("取消")
        self.cancel_task_button.setEnabled(False)
        self.task_detail_label = QLabel("")
        self.task_detail_label.setMinimumWidth(120)
        self.detail_button = QPushButton("详细信息")
        self.detail_button.setCheckable(True)
        self.detail_button.setToolTip("打开或收起详细任务日志")
        task_layout.addWidget(self.task_name_label)
        task_layout.addWidget(self.task_progress, 1)
        task_layout.addWidget(self.task_detail_label, 1)
        task_layout.addWidget(self.detail_button)
        task_layout.addWidget(self.cancel_task_button)
        root.addWidget(task_bar)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(120)
        self.log_box.setVisible(False)
        self.log_box.setPlaceholderText("日志（可展开查看后台任务和构建报告）")
        self.detail_button.toggled.connect(self.log_box.setVisible)
        root.addWidget(self.log_box)
        self.setCentralWidget(central)
        self.statusBar().showMessage("导入图片后，在画布上编辑区域")

        # The old public attribute names remain aliases for projects and tests
        # that used the deterministic window API before the canvas migration.
        for name in (
            "open_project_button",
            "save_project_button",
            "solid_mode_combo",
            "explicit_background_combo",
            "background_strength_slider",
            "background_strength_spin",
            "background_tolerance_spin",
            "edge_refinement_slider",
            "edge_refinement_spin",
            "refresh_solid_button",
            "remove_background_button",
            "sample_background_button",
            "selection_operation_combo",
            "apply_selection_button",
            "finish_polygon_button",
            "confirm_solid_button",
            "height_mode_combo",
            "height_relief_spin",
            "height_view_combo",
            "generate_height_button",
            "export_height_button",
            "low_percentile_spin",
            "high_percentile_spin",
            "black_point_spin",
            "white_point_spin",
            "midtone_spin",
            "invert_check",
            "fixed_height_spin",
            "line_depth_spin",
            "line_threshold_spin",
            "line_softness_spin",
            "height_amount_spin",
            "refresh_height_button",
            "reset_height_button",
            "confirm_height_button",
            "width_spin",
            "height_spin",
            "base_spin",
            "relief_spin_mesh",
            "minimum_thickness_spin",
            "min_feature_spin",
            "quality_combo",
            "format_combo",
            "build_button",
        ):
            setattr(self, name, getattr(self.controls, name))
        # Keep the old public mesh parameter name while making the height page
        # use its own visible relief-height control.
        self.relief_spin = self.controls.relief_spin_mesh
        self.source_preview = self.canvas
        self.solid_preview = self.canvas
        self.height_preview = self.canvas
        self.mesh_preview = self.canvas

    def _connect_signals(self):
        self.controls.action_requested.connect(self._action)
        self.controls.mode_requested.connect(self.set_mode)
        self.controls.tool_requested.connect(self.set_tool)
        self.controls.overlay_opacity_changed.connect(self._set_overlay_opacity)
        self.controls.layer_visibility_requested.connect(self.canvas.set_layer_visibility)
        self.height_view_combo.currentTextChanged.connect(self._set_height_view)
        self.controls.undo_button.clicked.connect(self.undo_current)
        self.controls.redo_button.clicked.connect(self.redo_current)
        self.cancel_task_button.clicked.connect(self.cancel_active_job)
        self.canvas.stroke_finished.connect(self._on_stroke_finished)
        self.canvas.polygon_finished.connect(self._on_polygon_finished)
        self.canvas.polygon_points_changed.connect(self._on_polygon_points_changed)
        self.canvas.zoom_changed.connect(self.controls.set_zoom_status)
        self.canvas.brush_size_changed.connect(self._on_canvas_brush_size_changed)
        for control in (
            self.solid_mode_combo,
            self.explicit_background_combo,
            self.background_strength_slider,
            self.edge_refinement_slider,
        ):
            signal = control.currentTextChanged if hasattr(control, "currentTextChanged") else control.valueChanged
            signal.connect(lambda *_: self._solid_parameters_changed())
        for control in (
            self.height_mode_combo,
            self.low_percentile_spin,
            self.high_percentile_spin,
            self.black_point_spin,
            self.white_point_spin,
            self.midtone_spin,
            self.invert_check,
            self.fixed_height_spin,
            self.line_depth_spin,
            self.line_threshold_spin,
            self.line_softness_spin,
        ):
            signal = control.currentTextChanged if hasattr(control, "currentTextChanged") else (
                control.toggled if hasattr(control, "toggled") else control.valueChanged
            )
            signal.connect(lambda *_: self._height_parameters_changed())
        self.canvas.set_brush_size_px(self.session.solid_brush_size_px)

    def _solid_parameters_changed(self):
        if self._loading_controls:
            return
        if self.session.solid_mask_confirmed:
            self.session.mark_solid_changed()
            self.session.editor_mode = EditorMode.SOLID
            self.canvas.cancel_interaction()
            self._update_state()
        self.solid_debouncer.trigger()

    def _height_parameters_changed(self):
        if self._loading_controls:
            return
        if self.session.height_master_confirmed:
            self.session.mark_height_changed()
            self.session.editor_mode = EditorMode.HEIGHT
            self.canvas.cancel_interaction()
            self._update_state()
        if self.session.height_draft is not None:
            self.height_debouncer.trigger()

    # --------------------------------------------------------------- utilities
    def _sync_aliases(self):
        self.source_data = self.session.source_data
        self.preview_source_data = self.session.preview_source_data
        self.solid_draft = self.session.solid_draft
        self.height_draft = self.session.height_draft
        self.solid_edits = self.session.solid_edits
        self.height_edits = self.session.height_edits
        self.solid_redo = self.session.solid_redo_stack
        self.height_redo = self.session.height_redo_stack
        self.solid_mask_confirmed = self.session.solid_mask_confirmed
        self.height_master_confirmed = self.session.height_master_confirmed
        self.artifact_directory = self.session.artifact_directory

    def _set_user_status(self, message: str, *, key: str | None = None):
        text = str(message).splitlines()[0].strip()
        if key is not None and key == self._last_status_key:
            return False
        self._last_status_key = key
        self.task_name_label.setText(text)
        self.statusBar().showMessage(text)
        return True

    def _log(self, message: str, payload: dict | None = None):
        text = str(message).strip()
        self._last_error_key = None
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        entry = f"[{timestamp}] {text}"
        if payload is not None:
            entry += "\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str)
        self._detail_log_entries.append(entry)
        self._detail_log_entries = self._detail_log_entries[-200:]
        self.log_box.setPlainText("\n\n".join(self._detail_log_entries))
        self._set_user_status(text)

    def _show_user_error(self, message: str, technical=None):
        key = str(message)
        if key == self._last_error_key:
            self._set_user_status(message, key=key)
            return False
        self._last_error_key = key
        if technical is None:
            payload = None
        elif isinstance(technical, dict):
            payload = dict(technical)
        else:
            payload = {"error": str(technical), "error_type": type(technical).__name__}
        self._log(message, payload)
        self._last_error_key = key
        self._set_user_status(message, key=key)
        return True

    def _show_error(self, title: str, error):
        message = f"{title}，请检查输入后重试"
        self._show_user_error(message, error)
        self._set_task("任务失败", str(error), busy=False)

    def _update_state(self):
        self._sync_aliases()
        if self.session.editor_mode == EditorMode.SOLID:
            solid_tools = {
                CanvasTool.BACKGROUND_SAMPLE,
                CanvasTool.BRUSH_ADD,
                CanvasTool.BRUSH_ERASE,
                CanvasTool.FILL,
                CanvasTool.RECTANGLE,
                CanvasTool.POLYGON,
            }
            if self.session.active_tool not in solid_tools:
                self.session.active_tool = CanvasTool.BRUSH_ADD
                self.canvas.set_tool(CanvasTool.BRUSH_ADD)
        elif self.session.editor_mode == EditorMode.HEIGHT:
            height_tools = {
                CanvasTool.HEIGHT_SET,
                CanvasTool.HEIGHT_RAISE,
                CanvasTool.HEIGHT_LOWER,
                CanvasTool.HEIGHT_SMOOTH,
            }
            if self.session.height_draft is not None:
                if self.session.active_tool not in height_tools:
                    self.session.active_tool = CanvasTool.HEIGHT_SET
                    self.canvas.set_tool(CanvasTool.HEIGHT_SET)
            else:
                self.canvas.set_tool("inactive")
        else:
            self.canvas.set_tool("inactive")
        self.controls.overlay_opacity_slider.blockSignals(True)
        self.controls.overlay_opacity_slider.setValue(round(self.session.overlay_opacity * 100.0))
        self.controls.overlay_opacity_slider.blockSignals(False)
        self.controls.set_approval_state(self.session.solid_mask_confirmed, self.session.height_master_confirmed)
        self.controls.set_mode(self.session.editor_mode)
        self.controls.set_stage_content(
            self.session.editor_mode,
            solid_exists=self.session.solid_draft is not None,
            height_exists=self.session.height_draft is not None,
        )
        self.canvas.set_mode_visibility(self.session.editor_mode.value)
        self.controls.solid_mode_combo.setEnabled(not self.session.solid_mask_confirmed)
        self.controls.height_mode_combo.setEnabled(self.session.solid_mask_confirmed and not self.session.height_master_confirmed)
        self.controls.mesh_status_label.setText(
            "高度已确认，可生成模型" if self.session.height_master_confirmed else "确认高度后可生成模型"
        )
        selected_size = self.session.height_brush_size_px if self.session.editor_mode == EditorMode.HEIGHT else self.session.solid_brush_size_px
        self.canvas.set_brush_size_px(selected_size)
        self.controls.set_brush_status(selected_size)
        if self.session.editor_mode == EditorMode.HEIGHT and self.session.height_draft is None:
            self.controls.set_tool_status("无（请先生成高度图）")
        elif self.session.editor_mode == EditorMode.MESH:
            self.controls.set_tool_status("无")
        else:
            self.controls.set_tool_status(TOOL_LABELS.get(self.session.active_tool, str(self.session.active_tool.value)))
        self.canvas.set_height_display_mode(self._height_view_key())

    def _height_view_key(self) -> str:
        value = self.height_view_combo.currentText()
        return {"原图": "source", "灰度图": "grayscale", "原图 + 灰度叠加": "overlay"}.get(value, "grayscale")

    def _set_height_view(self, value: str):
        self.canvas.set_height_display_mode({"原图": "source", "灰度图": "grayscale", "原图 + 灰度叠加": "overlay"}.get(str(value), "grayscale"))

    def _set_task(self, name: str, detail: str = "", *, busy: bool = True):
        self.task_name_label.setText(name)
        self.task_detail_label.setText(detail)
        self.cancel_task_button.setEnabled(bool(busy))
        if not busy:
            self.task_progress.setValue(0)

    def _render_canvas_layers(self):
        preview = self.session.preview_source_data
        if preview is None:
            return
        target_shape = preview.luminance.shape
        self.canvas.set_source_data(preview, fit=False)
        mask = self.session.solid_draft.mask if self.session.solid_draft is not None else None
        height = self.session.height_draft.height_master if self.session.height_draft is not None else None
        if mask is not None:
            mask = _resize_layer(mask, target_shape, mask=True)
        if height is not None:
            height = _resize_layer(height, target_shape)
        self.canvas.set_solid_mask(mask)
        self.canvas.set_height_master(height)

    # ---------------------------------------------------------------- actions
    def _action(self, action: str):
        if action == "open_image":
            self.import_image()
        elif action == "open_project":
            self.open_project()
        elif action == "save_project":
            self.save_project()
        elif action == "undo":
            self.undo_current()
        elif action == "redo":
            self.redo_current()
        elif action == "approve":
            self.confirm_solid() if self.session.editor_mode == EditorMode.SOLID else self.confirm_height()
        elif action == "build":
            self.build_and_export()
        elif action == "refresh_solid":
            self.refresh_solid()
        elif action == "remove_background":
            self.solid_mode_combo.setCurrentText("去除背景")
            self.refresh_solid()
        elif action == "sample_background":
            self.set_tool(CanvasTool.BACKGROUND_SAMPLE)
        elif action in {"refresh_height", "generate_height"}:
            self.refresh_height()
        elif action == "export_height":
            self.export_heightmap()
        elif action == "reset_height":
            self.reset_height_controls()
        elif action == "finish_polygon":
            self.canvas.finish_polygon()
        elif action == "apply_selection":
            self.apply_pending_selection()

    def set_mode(self, mode: EditorMode | str):
        selected = EditorMode(mode)
        if not self.session.request_mode(selected):
            if selected == EditorMode.HEIGHT:
                self._show_user_error("请先确认区域，再编辑高度。")
            elif selected == EditorMode.MESH:
                self._show_user_error("请先确认高度，再生成模型。")
            return False
        self.canvas.cancel_interaction()
        self._pending_region_selection = None
        self.canvas.set_selection(None)
        self._update_state()
        return True

    def set_tool(self, tool: CanvasTool | str):
        selected = CanvasTool(tool)
        if selected in {
            CanvasTool.HEIGHT_SET,
            CanvasTool.HEIGHT_RAISE,
            CanvasTool.HEIGHT_LOWER,
            CanvasTool.HEIGHT_SMOOTH,
        } and (self.session.editor_mode != EditorMode.HEIGHT or self.session.height_draft is None):
            self._show_user_error("请先生成高度图，再编辑高度。")
            return False
        if selected in {
            CanvasTool.BRUSH_ADD,
            CanvasTool.BRUSH_ERASE,
            CanvasTool.FILL,
            CanvasTool.RECTANGLE,
            CanvasTool.POLYGON,
        } and (self.session.editor_mode != EditorMode.SOLID or self.session.solid_draft is None):
            self._show_user_error("请先生成区域，再进行手工修正。")
            return False
        self.canvas.cancel_interaction()
        self.session.set_tool(selected)
        self.canvas.set_tool(selected)
        size = self.session.height_brush_size_px if self.session.editor_mode == EditorMode.HEIGHT else self.session.solid_brush_size_px
        self.canvas.set_brush_size_px(size)
        self.controls.set_active_tool(selected)
        self.controls.set_tool_status(TOOL_LABELS.get(selected, selected.value))
        self.controls.set_brush_status(size)
        return True

    def _set_brush_size(self, mode: str, value: int):
        selected = str(mode).lower()
        size = int(np.clip(int(value), self.canvas.MIN_BRUSH_SIZE_PX, self.canvas.MAX_BRUSH_SIZE_PX))
        if selected == "height":
            self.session.height_brush_size_px = size
        else:
            self.session.solid_brush_size_px = size
        active_size = self.session.height_brush_size_px if self.session.editor_mode == EditorMode.HEIGHT else self.session.solid_brush_size_px
        self.controls.set_brush_status(active_size)
        self.canvas.set_brush_size_px(active_size)

    def _on_canvas_brush_size_changed(self, value: int):
        mode = "height" if self.session.editor_mode == EditorMode.HEIGHT else "solid"
        self._set_brush_size(mode, int(value))

    def _set_overlay_opacity(self, value: float):
        self.session.overlay_opacity = float(np.clip(float(value), 0.0, 1.0))
        self.canvas.set_overlay_opacity(self.session.overlay_opacity)

    def undo_current(self):
        if self.session.editor_mode == EditorMode.SOLID:
            changed = self.session.undo(EditorMode.SOLID)
            if changed is not None:
                self._compute_solid_preview_sync()
        elif self.session.editor_mode == EditorMode.HEIGHT:
            changed = self.session.undo(EditorMode.HEIGHT)
            if changed is not None:
                self._compute_height_preview_sync()
        self._update_state()

    def redo_current(self):
        if self.session.editor_mode == EditorMode.SOLID:
            changed = self.session.redo(EditorMode.SOLID)
            if changed is not None:
                self._compute_solid_preview_sync()
        elif self.session.editor_mode == EditorMode.HEIGHT:
            changed = self.session.redo(EditorMode.HEIGHT)
            if changed is not None:
                self._compute_height_preview_sync()
        self._update_state()

    # --------------------------------------------------------------- import/io
    def import_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if path:
            self.load_image(path)

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开项目", "", "Project (project.json *.json)")
        if path:
            self.load_project(path)

    def load_image(self, path: str | Path):
        try:
            self.source_path = Path(path).resolve()
            source = load_source_image(self.source_path)
            preview = _preview_data(source)
            directory = self.source_path.parent / f"{self.source_path.stem}_relief_project"
            self.session.reset_for_source(source, preview, directory)
            self._render_canvas_layers()
            self.canvas.fit_to_window()
            self._set_brush_size("solid", self.session.solid_brush_size_px)
            self._set_brush_size("height", self.session.height_brush_size_px)
            self._log("图片已导入；编辑预览最长边限制为 1536 像素", {"path": str(self.source_path), "source_shape": list(source.luminance.shape), "preview_shape": list(preview.luminance.shape)})
            self.refresh_solid()
            self._update_state()
        except Exception as exc:
            self._show_error("导入失败", exc)

    def load_project(self, project_path: str | Path):
        try:
            loaded = load_workflow_artifacts(project_path, verify_hashes=True)
            project = loaded.project
            directory = Path(project_path).resolve().parent
            preview = _preview_data(loaded.source)
            self.source_path = Path(project.get("source_path") or directory / "source_aligned.png").resolve()
            if not self.source_path.exists():
                self.source_path = directory / "source_aligned.png"
            self.session.reset_for_source(loaded.source, preview, directory)
            self.session.solid_edits.extend(dict(item) for item in project.get("solid_mask_edits", ()) if isinstance(item, dict))
            self.session.height_edits.extend(dict(item) for item in project.get("height_edits", ()) if isinstance(item, dict))
            self.session.solid_undo_stack.extend(dict(item) for item in self.session.solid_edits)
            self.session.height_undo_stack.extend(dict(item) for item in self.session.height_edits)
            self.session.background_samples.extend(dict(item) for item in project.get("source_parameters", {}).get("background_samples", ()) if isinstance(item, dict))
            self.session.solid_draft = SolidMaskDraft(loaded.solid_mask, dict(project.get("solid_mask_report", {})))
            self.session.height_draft = HeightMasterDraft(loaded.height_master, np.zeros_like(loaded.solid_mask), dict(project.get("height_master_report", {})))
            self.session.formal_solid_mask = loaded.solid_mask.copy()
            self.session.formal_height_master = loaded.height_master.copy()
            self.session.solid_mask_confirmed = bool(project.get("solid_mask_confirmed"))
            self.session.height_master_confirmed = bool(project.get("height_master_confirmed"))
            self._loading_controls = True
            try:
                self._load_parameters(project.get("source_parameters", {}))
            finally:
                self._loading_controls = False
            state = project.get("canvas_state", {})
            self.session.overlay_opacity = float(state.get("overlay_opacity", 0.5))
            self.session.canvas_zoom = float(state.get("zoom", 1.0))
            self.session.solid_brush_size_px = int(np.clip(state.get("solid_brush_size_px", 24), 2, 300))
            self.session.height_brush_size_px = int(np.clip(state.get("height_brush_size_px", 24), 2, 300))
            requested_mode = str(state.get("mode", "height" if self.session.height_master_confirmed else "solid"))
            self.session.editor_mode = EditorMode(requested_mode) if requested_mode in {item.value for item in EditorMode} else EditorMode.SOLID
            if self.session.editor_mode == EditorMode.MESH and not self.session.height_master_confirmed:
                self.session.editor_mode = EditorMode.HEIGHT if self.session.solid_mask_confirmed else EditorMode.SOLID
            requested_view = str(state.get("height_view", "grayscale"))
            view_label = {"source": "原图", "grayscale": "灰度图", "overlay": "原图 + 灰度叠加"}.get(requested_view, "灰度图")
            self.height_view_combo.setCurrentText(view_label)
            self.canvas.set_overlay_opacity(self.session.overlay_opacity)
            self._render_canvas_layers()
            self.canvas.set_zoom(self.session.canvas_zoom)
            self._set_brush_size("solid", self.session.solid_brush_size_px)
            self._set_brush_size("height", self.session.height_brush_size_px)
            self._update_state()
            self._log("项目已重新打开，已恢复批准状态、编辑记录和正式主图", {"project": str(Path(project_path).resolve()), "editor_schema_version": project.get("editor_schema_version", 1), "solid_edit_count": len(self.session.solid_edits), "height_edit_count": len(self.session.height_edits)})
        except Exception as exc:
            self._show_error("打开项目失败", exc)

    def save_project(self):
        if self.source_data is None:
            return
        if self.session.artifact_directory is None:
            selected = QFileDialog.getExistingDirectory(self, "选择项目目录", str(self.source_path.parent if self.source_path else Path.cwd()))
            if not selected:
                return
            self.session.artifact_directory = Path(selected)
        try:
            self._ensure_formal_artifacts()
            artifacts = self._write_artifacts(self.session.artifact_directory)
            self._log("项目已保存", artifacts.report)
        except Exception as exc:
            self._show_error("保存失败", exc)

    save_artifacts = save_project

    def _load_parameters(self, parameters: dict):
        solid_mode = str(parameters.get("solid_mode", "auto_background"))
        for label, value in SOLID_MODE_OPTIONS.items():
            if value == solid_mode:
                self.solid_mode_combo.setCurrentText(label)
                break
        height_mode = str(parameters.get("height_mode", "bright_high"))
        for label, value in HEIGHT_MODE_OPTIONS.items():
            if value == height_mode:
                self.height_mode_combo.setCurrentText(label)
                break
        solid_settings = parameters.get("solid_settings", {})
        explicit = solid_settings.get("explicit_background")
        self.explicit_background_combo.setCurrentText("浅色" if explicit == "bright" else "深色" if explicit == "dark" else "自动")
        if "background_strength" in solid_settings:
            strength = float(solid_settings.get("background_strength", 8))
        else:
            tolerance = float(solid_settings.get("background_tolerance", 0.08))
            strength = tolerance / max(float(np.sqrt(3.0)), 1e-9) * 100.0
        self.background_strength_slider.setValue(int(np.clip(round(strength), 0, 100)))
        self.edge_refinement_slider.setValue(int(np.clip(round(float(solid_settings.get("edge_refinement_px", 0))), -20, 20)))
        normalization = parameters.get("normalization", {})
        for name, default in (("low_percentile", 2.0), ("high_percentile", 98.0), ("black_point", 0.0), ("white_point", 1.0), ("midtone", 1.0)):
            getattr(self, f"{name if name != 'low_percentile' else 'low_percentile'}_spin").setValue(float(normalization.get(name, default)))
        self.invert_check.setChecked(bool(normalization.get("invert", False)))
        height_settings = parameters.get("height_settings", {})
        self.fixed_height_spin.setValue(float(height_settings.get("fixed_height", 1.0)))
        self.height_relief_spin.setValue(float(height_settings.get("relief_height_mm", 3.0)))
        self.line_depth_spin.setValue(float(height_settings.get("line_depth_mm", 0.2)))
        self.line_threshold_spin.setValue(float(height_settings.get("line_threshold", 0.35)))
        self.line_softness_spin.setValue(float(height_settings.get("line_softness_px", 0.75)))
        mesh = parameters.get("mesh_settings", {})
        for key, attr, default in (("width_mm", "width_spin", 80.0), ("height_mm", "height_spin", 80.0), ("base_thickness_mm", "base_spin", 2.0), ("relief_height_mm", "relief_spin", 3.0), ("minimum_thickness_mm", "minimum_thickness_spin", 0.8), ("minimum_feature_mm", "min_feature_spin", 0.3)):
            getattr(self, attr).setValue(float(mesh.get(key, default)))
        for label, value in QUALITY_OPTIONS.items():
            if value == str(mesh.get("quality_mode", "standard")):
                self.quality_combo.setCurrentText(label)
                break
        export_format = str(mesh.get("export_format", "obj")).upper()
        if export_format in {"OBJ", "STL", "GLB"}:
            self.format_combo.setCurrentText(export_format)

    # -------------------------------------------------------------- parameters
    def _explicit_background(self):
        text = self.explicit_background_combo.currentText()
        return "bright" if text == "浅色" else "dark" if text == "深色" else None

    def _height_arguments(self, edits=None):
        return {
            "mode": HEIGHT_MODE_OPTIONS[self.height_mode_combo.currentText()],
            "low_percentile": float(self.low_percentile_spin.value()),
            "high_percentile": float(self.high_percentile_spin.value()),
            "black_point": float(self.black_point_spin.value()),
            "white_point": float(self.white_point_spin.value()),
            "midtone": float(self.midtone_spin.value()),
            "invert": bool(self.invert_check.isChecked()),
            "fixed_height": float(self.fixed_height_spin.value()),
            "line_threshold": float(self.line_threshold_spin.value()),
            "line_depth_mm": float(self.line_depth_spin.value()),
            "relief_height_mm": float(self.height_relief_spin.value()),
            "line_softness_px": float(self.line_softness_spin.value()),
            "height_edits": tuple(edits if edits is not None else self.session.height_edits),
        }

    def _solid_arguments(self, source, edits):
        return {
            "source": source,
            "mode": SOLID_MODE_OPTIONS[self.solid_mode_combo.currentText()],
            "background_samples": tuple(self.session.background_samples),
            "background_strength": float(self.background_strength_slider.value()),
            "explicit_background": self._explicit_background(),
            "explicit_threshold": 0.9 if self._explicit_background() == "bright" else 0.1,
            "edge_refinement_px": float(self.edge_refinement_slider.value()),
            "edge_refinement_reference_shape": tuple(self.source_data.luminance.shape) if self.source_data is not None else None,
            "edits": tuple(edits),
        }

    # ---------------------------------------------------------- background work
    def refresh_solid(self):
        if self.preview_source_data is None:
            return
        inputs = self._solid_arguments(self.preview_source_data, list(self.session.solid_edits))
        self._set_task("正在去除背景……", "编辑预览")
        self._solid_job_request = self.job_controller.submit("solid_draft", inputs, self._solid_worker)

    @staticmethod
    def _solid_worker(inputs, token: CancellationToken, progress):
        token.throw_if_cancelled()
        progress(15, "读取预览图")
        result = draft_solid_mask(**inputs)
        progress(100, "区域初稿完成")
        return result

    def _compute_solid_preview_sync(self):
        if self.preview_source_data is None:
            return None
        self.job_controller.invalidate("solid_draft")
        result = draft_solid_mask(**self._solid_arguments(self.preview_source_data, self.session.solid_edits))
        self.session.solid_draft = result
        self._render_canvas_layers()
        self._sync_aliases()
        return result

    def refresh_height(self, *, auto: bool = False):
        if self.preview_source_data is None:
            return
        if not self.session.solid_mask_confirmed:
            if not auto:
                self._show_user_error("请先确认区域，再生成高度图。")
            return
        if auto and self.session.height_draft is None:
            return
        mask = self.session.formal_solid_mask
        if mask is None:
            self._compute_solid_preview_sync()
            mask = self.session.solid_draft.mask
        preview_mask = _resize_layer(mask, self.preview_source_data.luminance.shape, mask=True)
        inputs = {
            "source": self.preview_source_data,
            "solid_mask": preview_mask,
            **self._height_arguments(),
        }
        self._set_task("正在生成高度图……", "编辑预览")
        self._height_job_request = self.job_controller.submit("height_draft", inputs, self._height_worker)

    @staticmethod
    def _height_worker(inputs, token: CancellationToken, progress):
        token.throw_if_cancelled()
        progress(15, "计算高度解释")
        result = draft_height_master(**inputs)
        progress(100, "高度初稿完成")
        return result

    def _compute_height_preview_sync(self):
        if self.preview_source_data is None or not self.session.solid_mask_confirmed:
            return None
        self.job_controller.invalidate("height_draft")
        base_mask = self.session.formal_solid_mask if self.session.formal_solid_mask is not None else self.session.solid_draft.mask
        mask = _resize_layer(base_mask, self.preview_source_data.luminance.shape, mask=True)
        result = draft_height_master(self.preview_source_data, mask, **self._height_arguments())
        self.session.height_draft = result
        self._render_canvas_layers()
        self._sync_aliases()
        return result

    # --------------------------------------------------------------- strokes
    def _on_stroke_finished(self, points):
        if not points or self.session.source_data is None:
            return
        tool = self.session.active_tool
        if tool == CanvasTool.BACKGROUND_SAMPLE:
            point = points[0]
            self.session.background_samples.append({"x": float(point[0]), "y": float(point[1]), "coordinate_space": "normalized"})
            self.solid_debouncer.trigger()
            self._log("已添加背景取样点")
            return
        if self.session.editor_mode == EditorMode.SOLID:
            radius = self.canvas.last_stroke_radius_normalized or self.canvas.screen_radius_to_normalized(
                self.session.solid_brush_size_px / 2.0
            )
            if tool == CanvasTool.BRUSH_ERASE:
                edit = normalized_edit_record("remove", points, radius)
            elif tool == CanvasTool.FILL:
                edit = {"operation": "fill", "shape": "circle", "x": float(points[0][0]), "y": float(points[0][1]), "coordinate_space": "normalized"}
            elif tool == CanvasTool.RECTANGLE:
                xs, ys = zip(*points)
                x0, x1 = min(xs), max(xs)
                y0, y1 = min(ys), max(ys)
                self._pending_region_selection = {
                    "shape": "rectangle",
                    "x": (x0 + x1) / 2.0,
                    "y": (y0 + y1) / 2.0,
                    "width_normalized": x1 - x0,
                    "height_normalized": y1 - y0,
                    "coordinate_space": "normalized",
                }
                self.canvas.set_selection((x0, y0, x1, y1))
                self._log("矩形已选择，请选择添加或擦除后应用")
                self._update_state()
                return
            elif tool == CanvasTool.POLYGON:
                self._pending_region_selection = {
                    "shape": "polygon",
                    "points": [list(point) for point in points],
                    "coordinate_space": "normalized",
                }
                self._log("多边形已选择，请选择添加或擦除后应用")
                self._update_state()
                return
            else:
                edit = normalized_edit_record("add", points, radius)
            self.session.add_solid_edit(edit)
            self._compute_solid_preview_sync()
            self._update_state()
            self._log("区域已更新")
            return
        if self.session.editor_mode == EditorMode.HEIGHT and self.session.solid_mask_confirmed:
            radius = self.canvas.last_stroke_radius_normalized or self.canvas.screen_radius_to_normalized(
                self.session.height_brush_size_px / 2.0
            )
            if tool == CanvasTool.HEIGHT_RAISE:
                edit = normalized_edit_record("add", points, radius, amount=float(self.height_amount_spin.value()))
            elif tool == CanvasTool.HEIGHT_LOWER:
                edit = normalized_edit_record("subtract", points, radius, amount=float(self.height_amount_spin.value()))
            elif tool == CanvasTool.HEIGHT_SMOOTH:
                edit = normalized_edit_record("smooth", points, radius, amount=float(self.height_amount_spin.value()))
            else:
                edit = normalized_edit_record("set", points, radius, value=float(self.fixed_height_spin.value()))
            self.session.add_height_edit(edit)
            self._compute_height_preview_sync()
            self._update_state()
            self._log("高度图已更新")

    def _on_polygon_points_changed(self, points):
        if points:
            self._set_user_status(f"多边形顶点：{len(points)}（双击或点击完成多边形）")

    def _on_polygon_finished(self, points):
        if len(points) < 3:
            self._show_user_error("多边形至少需要三个顶点。")
            return
        self._pending_region_selection = {
            "shape": "polygon",
            "points": [list(point) for point in points],
            "coordinate_space": "normalized",
        }
        self._log("多边形已选择，请选择添加或擦除后应用")
        self._update_state()

    def apply_pending_selection(self):
        pending = self._pending_region_selection
        if not isinstance(pending, dict):
            self._show_user_error("请先选择矩形或多边形区域。")
            return False
        operation = "remove" if self.controls.selection_operation_combo.currentText() == "擦除" else "add"
        edit = dict(pending)
        edit["operation"] = operation
        self.session.add_solid_edit(edit)
        self._pending_region_selection = None
        self.canvas.set_selection(None)
        self._compute_solid_preview_sync()
        self._update_state()
        self._log("区域已更新")
        return True

    # -------------------------------------------------------------- approvals
    def confirm_solid(self):
        if self.source_data is None:
            self._show_user_error("请先导入图片，再生成区域。")
            return False
        try:
            self._compute_solid_preview_sync()
            formal = draft_solid_mask(**self._solid_arguments(self.source_data, self.session.solid_edits))
            if not formal.mask.any():
                raise ValueError("保留区域为空")
            self.session.solid_draft = formal
            self.session.confirm_solid(formal.mask.copy())
            self.session.height_draft = None
            self.session.editor_mode = EditorMode.HEIGHT
            self._render_canvas_layers()
            self._update_state()
            self._log("区域已确认；现在可在同一画布编辑高度")
            return True
        except Exception as exc:
            self._show_error("批准实体失败", exc)
            return False

    def unlock_solid(self):
        self.session.mark_solid_changed()
        self.session.editor_mode = EditorMode.SOLID
        self._compute_solid_preview_sync()
        self._update_state()

    def confirm_height(self):
        if self.source_data is None or not self.session.solid_mask_confirmed:
            self._show_user_error("请先确认区域，再确认高度。")
            return False
        if self.session.height_draft is None:
            self._show_user_error("请先生成高度图，再确认高度。")
            return False
        try:
            formal_mask = self.session.formal_solid_mask
            if formal_mask is None:
                formal_mask = draft_solid_mask(**self._solid_arguments(self.source_data, self.session.solid_edits)).mask
                self.session.formal_solid_mask = formal_mask
            formal = draft_height_master(self.source_data, formal_mask, **self._height_arguments())
            self.session.height_draft = formal
            self.session.confirm_height(formal.height_master.copy())
            self._ensure_formal_artifacts()
            self._write_artifacts(self.session.artifact_directory)
            self.session.editor_mode = EditorMode.MESH
            self._render_canvas_layers()
            self._update_state()
            self._log("高度已确认；模型模式已解锁")
            return True
        except Exception as exc:
            self._show_error("批准高度失败", exc)
            return False

    def unlock_height(self):
        self.session.mark_height_changed()
        self.session.editor_mode = EditorMode.HEIGHT
        self._update_state()

    def reset_height_controls(self):
        defaults = {
            "height_mode_combo": "亮处更高",
            "low_percentile_spin": 2.0,
            "high_percentile_spin": 98.0,
            "black_point_spin": 0.0,
            "white_point_spin": 1.0,
            "midtone_spin": 1.0,
            "fixed_height_spin": 1.0,
            "line_depth_spin": 0.2,
            "line_threshold_spin": 0.35,
            "line_softness_spin": 0.75,
        }
        for name, value in defaults.items():
            control = getattr(self, name)
            if hasattr(control, "setCurrentText"):
                control.setCurrentText(value)
            else:
                control.setValue(value)
        self.invert_check.setChecked(False)
        if self.session.height_draft is not None:
            self.refresh_height()

    def export_heightmap(self):
        if self.source_data is None or not self.session.solid_mask_confirmed:
            self._show_user_error("请先确认区域，再导出灰度图。")
            return False
        if self.session.height_draft is None and self.session.formal_height_master is None:
            self._show_user_error("请先生成高度图，再导出灰度图。")
            return False
        start = str(self.session.artifact_directory or (self.source_path.parent if self.source_path else Path.cwd()))
        selected = QFileDialog.getExistingDirectory(self, "选择灰度图导出目录", start)
        if not selected:
            return False
        try:
            self._ensure_formal_artifacts()
            paths = export_grayscale_heightmaps(
                self.session.formal_height_master,
                self.session.formal_solid_mask,
                selected,
                include_tiff=True,
            )
            self.task_detail_label.setText(paths["height_master_16bit"])
            self._log("灰度图已导出", paths)
            return True
        except Exception as exc:
            self._show_error("灰度图导出失败", exc)
            return False

    # --------------------------------------------------------------- artifacts
    def replay_formal_edits(self):
        """Replay normalized canvas history against the original-resolution source."""
        if self.source_data is None:
            raise ValueError("source image is required")
        solid = draft_solid_mask(**self._solid_arguments(self.source_data, self.session.solid_edits))
        height = draft_height_master(self.source_data, solid.mask, **self._height_arguments())
        return solid, height

    def _ensure_formal_artifacts(self):
        if self.source_data is None:
            raise ValueError("source image is required")
        if self.session.formal_solid_mask is None and self.session.formal_height_master is None:
            solid, height = self.replay_formal_edits()
            self.session.formal_solid_mask = solid.mask
            self.session.formal_height_master = height.height_master
            self.session.solid_draft = solid
            self.session.height_draft = height
            return
        if self.session.formal_solid_mask is None:
            formal = draft_solid_mask(**self._solid_arguments(self.source_data, self.session.solid_edits))
            self.session.formal_solid_mask = formal.mask
            self.session.solid_draft = formal
        if self.session.formal_height_master is None:
            formal_height = draft_height_master(self.source_data, self.session.formal_solid_mask, **self._height_arguments())
            self.session.formal_height_master = formal_height.height_master
            self.session.height_draft = formal_height

    def _write_artifacts(self, directory: Path):
        self._ensure_formal_artifacts()
        source_parameters = {
            "solid_mode": SOLID_MODE_OPTIONS[self.solid_mode_combo.currentText()],
            "height_mode": HEIGHT_MODE_OPTIONS[self.height_mode_combo.currentText()],
            "background_samples": list(self.session.background_samples),
            "solid_settings": {
                "explicit_background": self._explicit_background(),
                "background_strength": int(self.background_strength_slider.value()),
                "background_tolerance": background_strength_to_tolerance(self.background_strength_slider.value()),
                "edge_refinement_px": int(self.edge_refinement_slider.value()),
            },
            "normalization": {"low_percentile": float(self.low_percentile_spin.value()), "high_percentile": float(self.high_percentile_spin.value()), "black_point": float(self.black_point_spin.value()), "white_point": float(self.white_point_spin.value()), "midtone": float(self.midtone_spin.value()), "invert": bool(self.invert_check.isChecked())},
            "height_settings": {"fixed_height": float(self.fixed_height_spin.value()), "line_threshold": float(self.line_threshold_spin.value()), "line_depth_mm": float(self.line_depth_spin.value()), "line_softness_px": float(self.line_softness_spin.value()), "relief_height_mm": float(self.height_relief_spin.value())},
            "mesh_settings": {"width_mm": float(self.width_spin.value()), "height_mm": float(self.height_spin.value()), "base_thickness_mm": float(self.base_spin.value()), "relief_height_mm": float(self.relief_spin.value()), "minimum_thickness_mm": float(self.minimum_thickness_spin.value()), "minimum_feature_mm": float(self.min_feature_spin.value()), "quality_mode": QUALITY_OPTIONS[self.quality_combo.currentText()], "export_format": self.format_combo.currentText().lower(), "mesh_type": "regular_shared_vertex_grid"},
        }
        artifacts = export_workflow_artifacts(
            self.source_data,
            self.session.formal_solid_mask,
            self.session.formal_height_master,
            directory,
            solid_mask_confirmed=self.session.solid_mask_confirmed,
            height_master_confirmed=self.session.height_master_confirmed,
            solid_report=self.session.solid_draft.report if self.session.solid_draft else None,
            height_report=self.session.height_draft.report if self.session.height_draft else None,
            source_parameters=source_parameters,
            solid_edits=self.session.solid_edits,
            height_edits=self.session.height_edits,
            canvas_state={
                "mode": self.session.editor_mode.value,
                "zoom": self.canvas.zoom,
                "overlay_opacity": self.canvas.overlay_opacity,
                "solid_brush_size_px": self.session.solid_brush_size_px,
                "height_brush_size_px": self.session.height_brush_size_px,
                "height_view": self._height_view_key(),
            },
        )
        self.session.artifact_directory = Path(directory)
        self._sync_aliases()
        return artifacts

    # ------------------------------------------------------------------- mesh
    def build_and_export(self, output_path: str | Path | None = None):
        if not (self.session.solid_mask_confirmed and self.session.height_master_confirmed):
            self._log("请先确认区域和高度")
            return False
        if output_path is None:
            suffix = self.format_combo.currentText().lower()
            default = self.session.artifact_directory / f"output.{suffix}" if self.session.artifact_directory else Path.cwd() / f"output.{suffix}"
            selected, _ = QFileDialog.getSaveFileName(self, "导出规则浮雕网格", str(default), f"{suffix.upper()} (*.{suffix})")
            if not selected:
                return False
            output_path = selected
        try:
            artifacts = self._write_artifacts(self.session.artifact_directory)
            preset = quality_preset(QUALITY_OPTIONS[self.quality_combo.currentText()])
            params = ReliefParameters(width_mm=float(self.width_spin.value()), height_mm=float(self.height_spin.value()), base_thickness_mm=float(self.base_spin.value()), relief_height_mm=float(self.relief_spin.value()), minimum_thickness_mm=float(self.minimum_thickness_spin.value()), max_grid_cells=int(preset["max_grid_cells"]), edge_style="straight")
            inputs = {"height_path": artifacts.paths["height_master_16bit"], "mask_path": artifacts.paths["solid_mask"], "output_path": str(output_path), "parameters": params, "quality_mode": preset["canonical_quality_mode"], "min_feature_mm": float(self.min_feature_spin.value()), "report_path": str(Path(self.session.artifact_directory) / "build_report.json")}
            self._set_task("正在生成模型……", "窗口和画布仍可操作")
            self._mesh_job_request = self.job_controller.submit("mesh_build", inputs, self._mesh_worker)
            return True
        except Exception as exc:
            self._show_error("构建准备失败", exc)
            return False

    @staticmethod
    def _mesh_worker(inputs, token: CancellationToken, progress):
        token.throw_if_cancelled()
        progress(10, "读取批准主图")
        result = build_relief_from_approved_heightmap(**inputs)
        progress(100, "网格导出完成")
        return result

    # ---------------------------------------------------------- job callbacks
    def _job_succeeded(self, result: JobResult):
        if result.job_type == "solid_draft":
            self.session.solid_draft = result.value
            self._render_canvas_layers()
            self._sync_aliases()
            self._log("区域初稿已生成")
        elif result.job_type == "height_draft":
            self.session.height_draft = result.value
            self._render_canvas_layers()
            self._sync_aliases()
            self._log("高度图已生成")
        elif result.job_type == "mesh_build":
            self.mesh_result = result.value
            report = getattr(result.value, "report", {}) or {}
            gate = report.get("manufacturing_gate", {}) if isinstance(report, dict) else {}
            self.controls.mesh_report_label.setText(
                f"生成完成\n制造检查：{gate.get('status', '未提供')}"
            )
            self._log("网格构建完成", report)
            self._set_task("就绪", "导出完成", busy=False)
            mesh_path = self.session.artifact_directory / "mesh_preview.png" if self.session.artifact_directory else None
            if mesh_path and mesh_path.is_file():
                self.canvas.set_mesh_preview(np.asarray(Image.open(mesh_path).convert("L")))
        self._update_state()

    def _job_started(self, request):
        self.session.active_job_id = int(request.request_id)
        self._sync_aliases()

    def _job_failed(self, error: JobError):
        if error.cancelled:
            self._set_task("任务已取消", "当前编辑内容未改变", busy=False)
            self._log("后台任务已取消")
        else:
            user_message = {
                "solid_draft": "区域生成失败，请检查图片或参数。",
                "height_draft": "高度图生成失败，请检查参数。",
                "mesh_build": "模型生成失败，请检查已确认的高度图。",
            }.get(error.job_type, "任务失败，请重试。")
            self._show_user_error(
                user_message,
                {"job_type": error.job_type, "request_id": error.request_id, "error": error.message},
            )
            self._set_task("任务失败", "请查看详细信息", busy=False)

    def _job_progress(self, request, percent, message):
        self.task_progress.setValue(int(percent))
        self.task_detail_label.setText(str(message))

    def _job_finished(self, request):
        if self.session.active_job_id == request.request_id:
            self.session.active_job_id = None
        if self.job_controller.is_latest(request.job_type, request.request_id) and request.job_type != "mesh_build":
            self._set_task("就绪", "", busy=False)

    def cancel_active_job(self):
        for request in (self._solid_job_request, self._height_job_request, self._mesh_job_request):
            if request is not None:
                self.job_controller.cancel(request.job_type, request.request_id)
        self._set_task("任务已取消", "当前编辑内容未改变", busy=False)

    def closeEvent(self, event):
        self.cancel_active_job()
        super().closeEvent(event)


def run_standalone():
    if QApplication is None:
        raise RuntimeError("PySide6 is required for the desktop application")
    app = QApplication.instance() or QApplication([])
    from .qt_text import install_readable_ui_font

    install_readable_ui_font(app)
    window = MainWindow()
    window.show()
    return int(app.exec())


__all__ = ["APP_TITLE", "APP_SUBTITLE", "HEIGHT_MODE_OPTIONS", "QUALITY_OPTIONS", "SOLID_MODE_OPTIONS", "MainWindow", "run_standalone"]
