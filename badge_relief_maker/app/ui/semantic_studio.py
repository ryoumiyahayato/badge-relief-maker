"""Focused semantic annotation studio layered on the existing Chinese UI.

The editor adds two explicit manual tools before model generation:

* part mode: click a detected region and classify it as empty, solid, higher or lower;
* brush mode: paint the same four meanings over uncertain or broken boundaries.

Edits are stored in the existing project fields and therefore survive reopening.
A stroke-group marker makes one drag gesture one undo step.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import uuid

try:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QComboBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QTextEdit,
        QWidget,
    )
except Exception:  # pragma: no cover
    QEvent = None
    Qt = None
    QFont = None
    QComboBox = None
    QFileDialog = None
    QFormLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QMessageBox = None
    QTextEdit = None
    QWidget = None

from ..core.project_build import build_side_relief_from_project, relief_parameters_from_project
from ..core.project_io import asset_root_for, resolve_project_asset, save_project
from ..core.project_model import ManualMarker
from ..core.single_side_pipeline import prepare_relief_field
from .grayscale_studio import APP_TITLE, MainWindow as BaseMainWindow


TOOL_OPTIONS = {
    "部件标注（单击整个区域）": "part",
    "笔刷标注（拖动涂抹）": "brush",
}
ROLE_OPTIONS = {
    "空（挖空）": "background",
    "实体（补填）": "solid",
    "较高": "raise",
    "较低": "recess",
}
BRUSH_OPTIONS = {
    "小": 0.012,
    "中": 0.026,
    "大": 0.052,
}
STRENGTH_OPTIONS = {
    "轻微": 0.06,
    "标准": 0.12,
    "明显": 0.20,
}
QUALITY_OPTIONS = {
    "快速预览（约25万网格点）": "preview",
    "精细模型（约120万网格点）": "standard",
    "极细模型（约240万网格点）": "high",
}
ROLE_LABELS = {
    "background": "空",
    "solid": "实体",
    "raise": "较高",
    "recess": "较低",
}


class MainWindow(BaseMainWindow):
    """Chinese semantic editor with part and freehand brush annotation."""

    def __init__(self):
        self._painting = False
        self._stroke_points = []
        super().__init__()
        self.setWindowTitle("勋章浮雕建模器")
        if QFont is not None:
            self.setFont(QFont("Segoe UI", 10))
        self._configure_semantic_ui()

    # ----------------------------------------------------------- UI setup
    def _configure_semantic_ui(self):
        self.phase_two_button.hide()
        self.region_operation_combo.hide()
        self.region_amount_spin.hide()
        self.region_radius_spin.hide()
        self.export_button.setText("确认标注并导出 Blender 模型")

        # Hide the old tutorial panel; the tool labels are now self-explanatory.
        for editor in self.findChildren(QTextEdit):
            if "操作顺序" in editor.toPlainText():
                editor.hide()

        self.tool_combo = QComboBox()
        self.tool_combo.addItems(TOOL_OPTIONS.keys())
        self.role_combo = QComboBox()
        self.role_combo.addItems(ROLE_OPTIONS.keys())
        self.brush_combo = QComboBox()
        self.brush_combo.addItems(BRUSH_OPTIONS.keys())
        self.brush_combo.setCurrentText("中")
        self.strength_combo = QComboBox()
        self.strength_combo.addItems(STRENGTH_OPTIONS.keys())
        self.strength_combo.setCurrentText("标准")
        self.model_quality_combo = QComboBox()
        self.model_quality_combo.addItems(QUALITY_OPTIONS.keys())
        self.model_quality_combo.setCurrentText("精细模型（约120万网格点）")

        semantic_group = QGroupBox("人工语义标注")
        form = QFormLayout(semantic_group)
        form.addRow("工具", self.tool_combo)
        form.addRow("标注含义", self.role_combo)
        form.addRow("笔刷大小", self.brush_combo)
        form.addRow("高低幅度", self.strength_combo)
        form.addRow("导出密度", self.model_quality_combo)
        legend = QLabel(
            "蓝：空　绿：实体　红：较高　紫：较低\n"
            "部件标注用于封闭区域；笔刷用于断线、毛边和识别不确定的位置。"
        )
        legend.setWordWrap(True)
        legend.setStyleSheet("color:#cbd5e1; padding:6px 2px;")
        form.addRow(legend)

        root_layout = self.centralWidget().layout()
        root_layout.insertWidget(2, semantic_group)

        try:
            self.region_preview.clicked.disconnect(self.apply_region_operation)
        except (TypeError, RuntimeError):
            pass
        self.region_preview.installEventFilter(self)
        self.region_preview.setMouseTracking(True)

        # The old quality selector controlled image export size. Keep it hidden;
        # the new selector communicates actual model density instead.
        self.quality_combo.hide()
        self._update_semantic_count()

    # ----------------------------------------------------------- mouse input
    def _normalized_position(self, event):
        rect = self.region_preview._target_rect()
        if rect is None:
            return None
        left, top, width, height = rect
        point = event.position()
        x = float(point.x())
        y = float(point.y())
        if not (left <= x <= left + width and top <= y <= top + height):
            return None
        return (
            min(max((x - left) / max(width, 1.0), 0.0), 1.0),
            min(max((y - top) / max(height, 1.0), 0.0), 1.0),
        )

    def eventFilter(self, watched, event):
        if watched is self.region_preview and QEvent is not None:
            kind = event.type()
            if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                point = self._normalized_position(event)
                if point is not None and self.project is not None:
                    self._painting = True
                    self._stroke_points = [point]
                    return True
            elif kind == QEvent.Type.MouseMove and self._painting:
                point = self._normalized_position(event)
                if point is not None and self._should_append_point(point):
                    self._stroke_points.append(point)
                return True
            elif kind == QEvent.Type.MouseButtonRelease and self._painting:
                point = self._normalized_position(event)
                if point is not None and self._should_append_point(point):
                    self._stroke_points.append(point)
                self._painting = False
                points = list(self._stroke_points)
                self._stroke_points = []
                if points:
                    self._commit_stroke(points)
                return True
        return super().eventFilter(watched, event)

    def _should_append_point(self, point):
        if not self._stroke_points:
            return True
        x0, y0 = self._stroke_points[-1]
        x1, y1 = point
        threshold = BRUSH_OPTIONS[self.brush_combo.currentText()] * 0.35
        return (x1 - x0) ** 2 + (y1 - y0) ** 2 >= threshold**2

    # ----------------------------------------------------------- annotations
    def _semantic_group_marker(self, stroke_id, role, tool):
        return ManualMarker(
            marker_type="semantic_stroke_group",
            target="front",
            data={"stroke_id": stroke_id, "role": role, "tool": tool},
        )

    def _commit_stroke(self, points):
        if self.project is None:
            return
        tool = TOOL_OPTIONS[self.tool_combo.currentText()]
        role = ROLE_OPTIONS[self.role_combo.currentText()]
        if tool == "part":
            points = [points[0]]
        elif self._artwork_interpretation == "lineart" and len(points) == 1:
            # A single click in brush mode is still a local brush, not a whole-part edit.
            tool = "brush"

        stroke_id = uuid.uuid4().hex
        if tool == "part" and self._artwork_interpretation == "lineart":
            self._append_part_annotation(points[0], role, stroke_id)
        else:
            self._append_brush_annotation(points, role, stroke_id)
        self.project.manual_markers.append(self._semantic_group_marker(stroke_id, role, tool))
        self._save_project()
        self._update_semantic_count()
        self.statusBar().showMessage(f"已保存一次“{ROLE_LABELS[role]}”标注，正在刷新预览。")
        self.generate_previews()

    def _append_part_annotation(self, point, role, stroke_id):
        x, y = point
        mapped_role = {"background": "background", "solid": "surface", "raise": "raise", "recess": "recess"}[role]
        self.project.front_relief.lineart_region_overrides.append(
            {
                "x": float(x),
                "y": float(y),
                "coordinate_space": "final_normalized",
                "role": mapped_role,
                "amount": STRENGTH_OPTIONS[self.strength_combo.currentText()],
                "stroke_id": stroke_id,
                "semantic_role": role,
            }
        )

    def _append_brush_annotation(self, points, role, stroke_id):
        if self._preview_transform is None:
            self._show_error("无法标注", "请先生成一次预览。")
            return
        radius = BRUSH_OPTIONS[self.brush_combo.currentText()]
        strength = STRENGTH_OPTIONS[self.strength_combo.currentText()]
        side = self.project.front_relief

        if role in {"background", "solid"}:
            operation = "remove" if role == "background" else "add"
            radius_pixel = self._preview_transform.target_radius_to_original(radius, normalized=True)
            for x, y in points:
                x_pixel, y_pixel = self._preview_transform.target_to_original_point(x, y, normalized=True)
                side.mask_edits.append(
                    {
                        "shape": "circle",
                        "x": float(x_pixel),
                        "y": float(y_pixel),
                        "radius_px": float(radius_pixel),
                        "coordinate_space": "pixel",
                        "operation": operation,
                        "stroke_id": stroke_id,
                        "semantic_role": role,
                    }
                )
            return

        operation = "add" if role == "raise" else "subtract"
        for x, y in points:
            self.project.manual_markers.append(
                ManualMarker(
                    marker_type="height",
                    target="front",
                    data={
                        "shape": "circle",
                        "x": float(x),
                        "y": float(y),
                        "radius_normalized": radius,
                        "coordinate_space": "final_normalized",
                        "operation": operation,
                        "value": strength,
                        "stroke_id": stroke_id,
                        "semantic_role": role,
                    },
                )
            )

    def undo_last_correction(self):
        if self.project is None:
            return
        groups = [m for m in self.project.manual_markers if m.marker_type == "semantic_stroke_group"]
        if not groups:
            return super().undo_last_correction()
        group = groups[-1]
        stroke_id = group.data.get("stroke_id")
        side = self.project.front_relief
        side.lineart_region_overrides = [item for item in side.lineart_region_overrides if item.get("stroke_id") != stroke_id]
        side.mask_edits = [item for item in side.mask_edits if item.get("stroke_id") != stroke_id]
        self.project.manual_markers = [
            marker
            for marker in self.project.manual_markers
            if marker is not group and marker.data.get("stroke_id") != stroke_id
        ]
        self._save_project()
        self._update_semantic_count()
        self.generate_previews()

    def _update_semantic_count(self):
        if self.project is None:
            self.correction_label.setText("人工标注：0 次")
            return
        groups = [m for m in self.project.manual_markers if m.marker_type == "semantic_stroke_group"]
        counts = {role: 0 for role in ROLE_LABELS}
        for marker in groups:
            role = marker.data.get("role")
            if role in counts:
                counts[role] += 1
        self.correction_label.setText(
            "人工标注："
            f"空 {counts['background']}　实体 {counts['solid']}　"
            f"较高 {counts['raise']}　较低 {counts['recess']}"
        )

    def _update_correction_count(self):
        self._update_semantic_count()

    # ----------------------------------------------------------- preview/export
    def generate_previews(self):
        record = self._source_record()
        if record is None or not self.project_path:
            return
        self._save_project()
        project = self.project
        project_path = self.project_path

        def operation():
            params, _ = relief_parameters_from_project(project, "front", "preview")
            source_path = resolve_project_asset(project_path, record.path)
            preview_dir = asset_root_for(project_path) / "previews" / "semantic_studio"
            preview_dir.mkdir(parents=True, exist_ok=True)
            prepared = prepare_relief_field(source_path, params, preview_dir=preview_dir)
            return prepared, str(source_path)

        self._run_task("正在应用人工标注并刷新预览…", operation, self._preview_ready)

    def _preview_ready(self, payload):
        super()._preview_ready(payload)
        self._update_semantic_count()
        self.summary_box.append("\n边缘处理：窄带轮廓净化 + 有符号距离场重采样。")

    def export_heightmap(self):
        if self.project is None or not self.project_path or QFileDialog is None:
            return
        default = Path(self.output_directory or Path(self.project_path).parent) / f"{self.project.name}.glb"
        selected, _ = QFileDialog.getSaveFileName(self, "导出 Blender 模型", str(default), "Blender GLB 模型 (*.glb)")
        if not selected:
            return
        if not selected.lower().endswith(".glb"):
            selected += ".glb"
        selected_path = Path(selected).resolve()
        selected_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_directory = str(selected_path.parent)
        self._save_settings()
        self._save_project()
        quality = QUALITY_OPTIONS[self.model_quality_combo.currentText()]
        project = self.project
        project_path = self.project_path

        def operation():
            result = build_side_relief_from_project(
                project,
                project_path,
                "front",
                export_format="glb",
                quality_mode=quality,
                export_name=selected_path.stem,
            )
            save_project(project, project_path)
            shutil.copy2(result.output_path, selected_path)
            result.report["user_output_path"] = str(selected_path)
            return result

        self._run_task("正在生成可导入 Blender 的封闭 GLB 模型…", operation, self._model_ready)

    def _model_ready(self, result):
        report = result.report
        path = report.get("user_output_path", result.output_path)
        self.open_folder_button.setEnabled(True)
        self.summary_box.setPlainText(
            "Blender 模型导出完成。\n"
            f"文件：{path}\n"
            f"顶点：{report.get('vertex_count', report.get('repaired_vertex_count', '未知'))}\n"
            f"三角面：{report.get('face_count', report.get('repaired_face_count', '未知'))}\n"
            f"网格：{report.get('mesh_grid_shape', '未知')}\n"
            "人工标注已经进入实体蒙版和高度场。"
        )
        self.statusBar().showMessage("GLB 已导出，可直接拖入 Blender。")
        if QMessageBox is not None:
            QMessageBox.information(self, APP_TITLE, f"模型导出完成：\n{path}")

    def show_phase_information(self):
        if QMessageBox is not None:
            QMessageBox.information(
                self,
                "人工标注说明",
                "先用部件或笔刷把不确定区域标成空、实体、较高或较低，确认预览后直接导出 GLB。",
            )
