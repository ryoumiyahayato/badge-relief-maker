"""Default canvas-first deterministic relief editor."""

from __future__ import annotations

import json
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
    draft_height_master,
    draft_solid_mask,
    export_workflow_artifacts,
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
APP_SUBTITLE = "实体蒙版 → 高度主图 → 规则网格；批准后网格只读取正式主图"
SOLID_MODE_OPTIONS = {
    "整个底板": "whole_plate",
    "自动去背景": "auto_background",
    "自定义实体范围": "custom",
}
HEIGHT_MODE_OPTIONS = {
    "亮色凸起": "bright_high",
    "暗色凸起": "dark_high",
    "线条凹刻": "line_engrave",
    "线条凸起": "line_emboss",
    "固定高度": "fixed",
}
QUALITY_OPTIONS = {"草稿": "draft", "标准": "standard", "精细": "fine"}


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
        self.session = EditorSession()
        self.editor_session = self.session
        self.source_path: Path | None = None
        self.mesh_result = None
        self._solid_job_request = None
        self._height_job_request = None
        self._mesh_job_request = None
        self._build_ui()
        self._connect_signals()
        self.job_controller = JobController(self)
        self.job_controller.job_started.connect(self._job_started)
        self.job_controller.succeeded.connect(self._job_succeeded)
        self.job_controller.failed.connect(self._job_failed)
        self.job_controller.progress.connect(self._job_progress)
        self.job_controller.finished.connect(self._job_finished)
        self.solid_debouncer = DebouncedJob(lambda _payload: self.refresh_solid(), self, 200)
        self.height_debouncer = DebouncedJob(lambda _payload: self.refresh_height(), self, 200)
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
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 100)
        self.task_progress.setValue(0)
        self.task_progress.setTextVisible(False)
        self.cancel_task_button = QPushButton("取消")
        self.cancel_task_button.setEnabled(False)
        self.task_detail_label = QLabel("")
        task_layout.addWidget(self.task_name_label)
        task_layout.addWidget(self.task_progress, 1)
        task_layout.addWidget(self.task_detail_label, 1)
        task_layout.addWidget(self.cancel_task_button)
        root.addWidget(task_bar)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(120)
        self.log_box.setPlaceholderText("日志（可展开查看后台任务和构建报告）")
        root.addWidget(self.log_box)
        self.setCentralWidget(central)
        self.statusBar().showMessage("导入图片后，在画布上编辑实体蒙版")

        # The old public attribute names remain aliases for projects and tests
        # that used the deterministic window API before the canvas migration.
        for name in (
            "open_project_button",
            "save_project_button",
            "solid_mode_combo",
            "explicit_background_combo",
            "background_tolerance_spin",
            "solid_radius_spin",
            "refresh_solid_button",
            "confirm_solid_button",
            "height_mode_combo",
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
            "height_radius_spin",
            "height_amount_spin",
            "refresh_height_button",
            "reset_height_button",
            "confirm_height_button",
            "width_spin",
            "height_spin",
            "base_spin",
            "relief_spin",
            "minimum_thickness_spin",
            "min_feature_spin",
            "quality_combo",
            "format_combo",
            "build_button",
        ):
            setattr(self, name, getattr(self.controls, name))
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
        self.controls.undo_button.clicked.connect(self.undo_current)
        self.controls.redo_button.clicked.connect(self.redo_current)
        self.cancel_task_button.clicked.connect(self.cancel_active_job)
        self.canvas.stroke_finished.connect(self._on_stroke_finished)
        for control in (self.solid_mode_combo, self.explicit_background_combo, self.background_tolerance_spin):
            signal = control.currentTextChanged if hasattr(control, "currentTextChanged") else control.valueChanged
            signal.connect(lambda *_: self.solid_debouncer.trigger())
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
            signal.connect(lambda *_: self.height_debouncer.trigger())

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

    def _log(self, message: str, payload: dict | None = None):
        text = str(message)
        if payload is not None:
            text += "\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str)
        self.log_box.append(text)
        self.statusBar().showMessage(str(message).splitlines()[0])

    def _show_error(self, title: str, error):
        self._log(f"{title}: {error}")
        self.task_name_label.setText("任务失败")
        self.task_detail_label.setText(f"{type(error).__name__}: {error}")

    def _update_state(self):
        self._sync_aliases()
        self.controls.overlay_opacity_slider.blockSignals(True)
        self.controls.overlay_opacity_slider.setValue(round(self.session.overlay_opacity * 100.0))
        self.controls.overlay_opacity_slider.blockSignals(False)
        self.controls.set_approval_state(self.session.solid_mask_confirmed, self.session.height_master_confirmed)
        self.controls.set_mode(self.session.editor_mode)
        self.canvas.set_mode_visibility(self.session.editor_mode.value)
        self.controls.solid_mode_combo.setEnabled(not self.session.solid_mask_confirmed)
        self.controls.height_mode_combo.setEnabled(self.session.solid_mask_confirmed and not self.session.height_master_confirmed)
        self.controls.mesh_status_label.setText(
            "已批准主图；网格只读取 solid_mask 和 height_master" if self.session.height_master_confirmed else "批准高度后可构建"
        )

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
        elif action == "refresh_height":
            self.refresh_height()
        elif action == "reset_height":
            self.reset_height_controls()

    def set_mode(self, mode: EditorMode | str):
        selected = EditorMode(mode)
        if not self.session.request_mode(selected):
            self._log("当前批准状态不允许进入该模式")
            return False
        self._update_state()
        return True

    def set_tool(self, tool: CanvasTool | str):
        selected = CanvasTool(tool)
        self.session.set_tool(selected)
        self.canvas.set_tool(selected)
        if selected in {CanvasTool.HEIGHT_SET, CanvasTool.HEIGHT_RAISE, CanvasTool.HEIGHT_LOWER, CanvasTool.HEIGHT_SMOOTH}:
            self.set_mode(EditorMode.HEIGHT)
        elif selected not in {CanvasTool.PAN, CanvasTool.BACKGROUND_SAMPLE} and self.session.editor_mode != EditorMode.SOLID:
            if self.session.solid_mask_confirmed:
                self.set_mode(EditorMode.HEIGHT)
        radius = self.height_radius_spin.value() if self.session.editor_mode == EditorMode.HEIGHT else self.solid_radius_spin.value()
        self.canvas.set_brush_radius(radius)

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
            self._load_parameters(project.get("source_parameters", {}))
            state = project.get("canvas_state", {})
            self.session.overlay_opacity = float(state.get("overlay_opacity", 0.5))
            self.session.canvas_zoom = float(state.get("zoom", 1.0))
            requested_mode = str(state.get("mode", "height" if self.session.height_master_confirmed else "solid"))
            self.session.editor_mode = EditorMode(requested_mode) if requested_mode in {item.value for item in EditorMode} else EditorMode.SOLID
            if self.session.editor_mode == EditorMode.MESH and not self.session.height_master_confirmed:
                self.session.editor_mode = EditorMode.HEIGHT if self.session.solid_mask_confirmed else EditorMode.SOLID
            self.canvas.set_overlay_opacity(self.session.overlay_opacity)
            self._render_canvas_layers()
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
        self.explicit_background_combo.setCurrentText("亮背景" if explicit == "bright" else "暗背景" if explicit == "dark" else "自动判断边缘背景")
        self.background_tolerance_spin.setValue(float(solid_settings.get("background_tolerance", 0.08)))
        normalization = parameters.get("normalization", {})
        for name, default in (("low_percentile", 2.0), ("high_percentile", 98.0), ("black_point", 0.0), ("white_point", 1.0), ("midtone", 1.0)):
            getattr(self, f"{name if name != 'low_percentile' else 'low_percentile'}_spin").setValue(float(normalization.get(name, default)))
        self.invert_check.setChecked(bool(normalization.get("invert", False)))
        height_settings = parameters.get("height_settings", {})
        self.fixed_height_spin.setValue(float(height_settings.get("fixed_height", 1.0)))
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
        return "bright" if text == "亮背景" else "dark" if text == "暗背景" else None

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
            "relief_height_mm": float(self.relief_spin.value()),
            "line_softness_px": float(self.line_softness_spin.value()),
            "height_edits": tuple(edits if edits is not None else self.session.height_edits),
        }

    def _solid_arguments(self, source, edits):
        return {
            "source": source,
            "mode": SOLID_MODE_OPTIONS[self.solid_mode_combo.currentText()],
            "background_samples": tuple(self.session.background_samples),
            "background_tolerance": float(self.background_tolerance_spin.value()),
            "explicit_background": self._explicit_background(),
            "explicit_threshold": 0.9 if self._explicit_background() == "bright" else 0.1,
            "edits": tuple(edits),
        }

    # ---------------------------------------------------------- background work
    def refresh_solid(self):
        if self.preview_source_data is None:
            return
        inputs = self._solid_arguments(self.preview_source_data, list(self.session.solid_edits))
        self._set_task("正在生成实体初稿……", "编辑预览")
        self._solid_job_request = self.job_controller.submit("solid_draft", inputs, self._solid_worker)

    @staticmethod
    def _solid_worker(inputs, token: CancellationToken, progress):
        token.throw_if_cancelled()
        progress(15, "读取预览图")
        result = draft_solid_mask(**inputs)
        progress(100, "实体初稿完成")
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

    def refresh_height(self):
        if self.preview_source_data is None or not self.session.solid_mask_confirmed:
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
        self._set_task("正在生成高度初稿……", "编辑预览")
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
        if tool == CanvasTool.PAN:
            return
        if tool == CanvasTool.BACKGROUND_SAMPLE:
            point = points[0]
            self.session.background_samples.append({"x": float(point[0]), "y": float(point[1]), "coordinate_space": "normalized"})
            self.solid_debouncer.trigger()
            self._log("已添加背景取样点")
            return
        if self.session.editor_mode == EditorMode.SOLID:
            radius = float(self.solid_radius_spin.value())
            if tool == CanvasTool.BRUSH_ERASE:
                edit = normalized_edit_record("remove", points, radius)
            elif tool == CanvasTool.FILL:
                edit = {"operation": "fill", "shape": "circle", "x": float(points[0][0]), "y": float(points[0][1]), "coordinate_space": "normalized"}
            elif tool == CanvasTool.RECTANGLE:
                xs, ys = zip(*points)
                edit = {"operation": "add", "shape": "rectangle", "x": (min(xs) + max(xs)) / 2.0, "y": (min(ys) + max(ys)) / 2.0, "width_normalized": max(xs) - min(xs), "height_normalized": max(ys) - min(ys), "coordinate_space": "normalized"}
            elif tool == CanvasTool.POLYGON:
                edit = {"operation": "add", "shape": "polygon", "points": [list(point) for point in points], "coordinate_space": "normalized"}
            else:
                edit = normalized_edit_record("add", points, radius)
            self.session.add_solid_edit(edit)
            self._compute_solid_preview_sync()
            self._update_state()
            return
        if self.session.editor_mode == EditorMode.HEIGHT and self.session.solid_mask_confirmed:
            radius = float(self.height_radius_spin.value())
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

    # -------------------------------------------------------------- approvals
    def confirm_solid(self):
        if self.source_data is None:
            return False
        try:
            self._compute_solid_preview_sync()
            formal = draft_solid_mask(**self._solid_arguments(self.source_data, self.session.solid_edits))
            if not formal.mask.any():
                raise ValueError("实体蒙版为空")
            self.session.solid_draft = formal
            self.session.confirm_solid(formal.mask.copy())
            self._compute_height_preview_sync()
            self.session.editor_mode = EditorMode.HEIGHT
            self._render_canvas_layers()
            self._update_state()
            self._log("实体蒙版已批准；现在可在同一画布编辑高度")
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
            self._log("高度主图已批准；网格模式已解锁")
            return True
        except Exception as exc:
            self._show_error("批准高度失败", exc)
            return False

    def unlock_height(self):
        self.session.mark_height_changed()
        self.session.editor_mode = EditorMode.HEIGHT
        self._update_state()

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
            "solid_settings": {"explicit_background": self._explicit_background(), "background_tolerance": float(self.background_tolerance_spin.value())},
            "normalization": {"low_percentile": float(self.low_percentile_spin.value()), "high_percentile": float(self.high_percentile_spin.value()), "black_point": float(self.black_point_spin.value()), "white_point": float(self.white_point_spin.value()), "midtone": float(self.midtone_spin.value()), "invert": bool(self.invert_check.isChecked())},
            "height_settings": {"fixed_height": float(self.fixed_height_spin.value()), "line_threshold": float(self.line_threshold_spin.value()), "line_depth_mm": float(self.line_depth_spin.value()), "line_softness_px": float(self.line_softness_spin.value())},
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
            canvas_state={"mode": self.session.editor_mode.value, "zoom": self.canvas.zoom, "overlay_opacity": self.canvas.overlay_opacity},
        )
        self.session.artifact_directory = Path(directory)
        self._sync_aliases()
        return artifacts

    # ------------------------------------------------------------------- mesh
    def build_and_export(self, output_path: str | Path | None = None):
        if not (self.session.solid_mask_confirmed and self.session.height_master_confirmed):
            self._log("请先批准实体蒙版和高度主图")
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
            self._set_task("正在构建规则网格……", "窗口和画布仍可操作")
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
        elif result.job_type == "height_draft":
            self.session.height_draft = result.value
            self._render_canvas_layers()
            self._sync_aliases()
        elif result.job_type == "mesh_build":
            self.mesh_result = result.value
            report = getattr(result.value, "report", {}) or {}
            self.controls.mesh_report_label.setText(json.dumps(report, ensure_ascii=False, indent=2, default=str)[:2000])
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
            self._set_task("任务失败", error.message, busy=False)
            self._log("后台任务失败", {"job_type": error.job_type, "request_id": error.request_id, "error": error.message})

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
    window = MainWindow()
    window.show()
    return int(app.exec())


__all__ = ["APP_TITLE", "APP_SUBTITLE", "HEIGHT_MODE_OPTIONS", "QUALITY_OPTIONS", "SOLID_MODE_OPTIONS", "MainWindow", "run_standalone"]
