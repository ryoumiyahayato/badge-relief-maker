"""Manual semantic review studio for badge and medal relief reconstruction.

The window keeps the existing project and processing backend, but changes the
interaction model from opaque numeric correction into explicit semantic review:

* click a detected part or paint a freehand stroke;
* mark it as void, a fixed relief level, relatively raised or relatively recessed;
* optionally lock the accepted result so later automatic regeneration cannot
  replace the user's decision;
* inspect a confidence heatmap and a physical cross-section before exporting GLB.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import uuid

try:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QTextEdit,
    )
except Exception:  # pragma: no cover - core-only installs may import constants
    QEvent = None
    Qt = None
    QFont = None
    QCheckBox = None
    QComboBox = None
    QDoubleSpinBox = None
    QFileDialog = None
    QFormLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QMessageBox = None
    QPushButton = None
    QTextEdit = None

from ..core.confidence_preview import build_uncertainty_map, save_focused_region_preview, save_uncertainty_preview
from ..core.lineart_region_graph import analyze_lineart_regions
from ..core.profile_inspection import sample_height_profile, save_height_profile_preview
from ..core.project_build import build_side_relief_from_project, relief_parameters_from_project
from ..core.project_io import asset_root_for, resolve_project_asset, save_project
from ..core.project_model import ManualMarker
from ..core.single_side_pipeline import prepare_relief_field
from .grayscale_studio import APP_TITLE, MainWindow as BaseMainWindow, _ImagePanel


TOOL_OPTIONS = {
    "部件标注（单击整个区域）": "part",
    "笔刷标注（拖动涂抹）": "brush",
}
ROLE_OPTIONS = {
    "空（挖空）": {"semantic_role": "background", "kind": "topology"},
    "实体补填／底面": {"semantic_role": "level_base", "kind": "absolute", "height": 0.18},
    "低层浮雕": {"semantic_role": "level_low", "kind": "absolute", "height": 0.34},
    "中层浮雕": {"semantic_role": "level_mid", "kind": "absolute", "height": 0.52},
    "高层浮雕": {"semantic_role": "level_high", "kind": "absolute", "height": 0.72},
    "最高构件": {"semantic_role": "level_top", "kind": "absolute", "height": 0.90},
    "相对抬高": {"semantic_role": "raise", "kind": "relative", "operation": "add"},
    "相对压低": {"semantic_role": "recess", "kind": "relative", "operation": "subtract"},
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
REVIEW_OPTIONS = {
    "区域语义图": "regions",
    "识别置信度热图": "uncertainty",
    "实体蒙版": "mask",
}
ROLE_LABELS = {
    "background": "空",
    "level_base": "底面",
    "level_low": "低层",
    "level_mid": "中层",
    "level_high": "高层",
    "level_top": "最高",
    "raise": "抬高",
    "recess": "压低",
}


class MainWindow(BaseMainWindow):
    """Chinese semantic editor with guided review and direct GLB export."""

    def __init__(self):
        self._painting = False
        self._stroke_points = []
        self._prepared_preview = None
        self._preview_paths = {}
        self._review_regions = []
        self._review_region_index = -1
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
        self.lock_check = QCheckBox("锁定已确认区域")
        self.lock_check.setChecked(True)
        self.review_combo = QComboBox()
        self.review_combo.addItems(REVIEW_OPTIONS.keys())
        self.next_issue_button = QPushButton("下一个待确认区域")
        self.model_quality_combo = QComboBox()
        self.model_quality_combo.addItems(QUALITY_OPTIONS.keys())
        self.model_quality_combo.setCurrentText("精细模型（约120万网格点）")

        semantic_group = QGroupBox("人工语义标注与复核")
        form = QFormLayout(semantic_group)
        form.addRow("工具", self.tool_combo)
        form.addRow("标注含义", self.role_combo)
        form.addRow("笔刷大小", self.brush_combo)
        form.addRow("相对修正幅度", self.strength_combo)
        form.addRow("", self.lock_check)
        form.addRow("检查视图", self.review_combo)
        form.addRow("", self.next_issue_button)
        form.addRow("导出密度", self.model_quality_combo)
        legend = QLabel(
            "蓝：空　青绿：底面／低层　黄橙：中高层　红：最高／抬高　紫：压低\n"
            "绝对层级适合字母、枝叶、飘带和主体构件；相对修正用于局部微调。"
        )
        legend.setWordWrap(True)
        legend.setStyleSheet("color:#cbd5e1; padding:6px 2px;")
        form.addRow(legend)

        root_layout = self.centralWidget().layout()
        root_layout.insertWidget(2, semantic_group)

        self.section_orientation_combo = QComboBox()
        self.section_orientation_combo.addItems(["水平截面", "垂直截面"])
        self.section_position_spin = QDoubleSpinBox()
        self.section_position_spin.setRange(0.0, 100.0)
        self.section_position_spin.setSingleStep(1.0)
        self.section_position_spin.setValue(50.0)
        self.section_position_spin.setSuffix(" %")
        section_controls = QHBoxLayout()
        section_controls.addWidget(QLabel("高度剖面"))
        section_controls.addWidget(self.section_orientation_combo)
        section_controls.addWidget(QLabel("位置"))
        section_controls.addWidget(self.section_position_spin)
        section_controls.addStretch(1)
        self.section_preview = _ImagePanel("高度剖面")
        self.section_preview.setMinimumSize(320, 150)
        self.section_preview.setMaximumHeight(210)
        workspace_layout = self.summary_box.parentWidget().layout()
        workspace_layout.insertLayout(1, section_controls)
        workspace_layout.insertWidget(2, self.section_preview)

        try:
            self.region_preview.clicked.disconnect(self.apply_region_operation)
        except (TypeError, RuntimeError):
            pass
        self.region_preview.installEventFilter(self)
        self.region_preview.setMouseTracking(True)
        self.quality_combo.hide()

        self.review_combo.currentTextChanged.connect(self._refresh_review_image)
        self.next_issue_button.clicked.connect(self.focus_next_issue)
        self.section_orientation_combo.currentTextChanged.connect(self._refresh_profile_preview)
        self.section_position_spin.valueChanged.connect(self._refresh_profile_preview)
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
    def _selected_role(self):
        return dict(ROLE_OPTIONS[self.role_combo.currentText()])

    def _semantic_group_marker(self, stroke_id, role, tool):
        return ManualMarker(
            marker_type="semantic_stroke_group",
            target="front",
            data={
                "stroke_id": stroke_id,
                "role": role["semantic_role"],
                "tool": tool,
                "locked": bool(self.lock_check.isChecked()),
            },
        )

    def _commit_stroke(self, points):
        if self.project is None:
            return
        tool = TOOL_OPTIONS[self.tool_combo.currentText()]
        role = self._selected_role()
        if tool == "part":
            points = [points[0]]

        stroke_id = uuid.uuid4().hex
        if tool == "part" and self._artwork_interpretation == "lineart":
            applied = self._append_part_annotation(points[0], role, stroke_id)
        else:
            applied = self._append_brush_annotation(points, role, stroke_id)
        if not applied:
            return

        self.project.manual_markers.append(self._semantic_group_marker(stroke_id, role, tool))
        self._save_project()
        self._update_semantic_count()
        label = ROLE_LABELS[role["semantic_role"]]
        self.statusBar().showMessage(f"已保存一次“{label}”标注，正在刷新预览。")
        self.generate_previews()

    def _append_part_annotation(self, point, role, stroke_id):
        x, y = point
        data = {
            "x": float(x),
            "y": float(y),
            "coordinate_space": "final_normalized",
            "stroke_id": stroke_id,
            "semantic_role": role["semantic_role"],
            "locked": bool(self.lock_check.isChecked()),
        }
        if role["kind"] == "topology":
            data["role"] = "background"
        elif role["kind"] == "absolute":
            data.update(
                {
                    "role": "raise",
                    "peak_height": float(role["height"]),
                    "profile_exponent": 0.12,
                    "detail_mix": 0.02,
                }
            )
        else:
            data.update(
                {
                    "role": "raise" if role["operation"] == "add" else "recess",
                    "amount": STRENGTH_OPTIONS[self.strength_combo.currentText()],
                }
            )
        self.project.front_relief.lineart_region_overrides.append(data)
        return True

    def _append_brush_annotation(self, points, role, stroke_id):
        if self._preview_transform is None:
            self._show_error("无法标注", "请先生成一次预览。")
            return False
        radius = BRUSH_OPTIONS[self.brush_combo.currentText()]
        side = self.project.front_relief
        locked = bool(self.lock_check.isChecked())

        if role["kind"] == "topology":
            self._append_mask_stroke(points, radius, "remove", role["semantic_role"], stroke_id)
            return True

        if role["kind"] == "absolute":
            self._append_mask_stroke(points, radius, "add", role["semantic_role"], stroke_id)
            operation = "set"
            value = float(role["height"])
        else:
            operation = str(role["operation"])
            value = STRENGTH_OPTIONS[self.strength_combo.currentText()]

        for x, y in points:
            side.region_layers.append(
                {
                    "shape": "circle",
                    "x": float(x),
                    "y": float(y),
                    "radius_normalized": radius,
                    "coordinate_space": "final_normalized",
                    "operation": operation,
                    "value": float(value),
                    "profile": "flat",
                    "feather_normalized": radius * 0.22,
                    "locked": locked,
                    "stroke_id": stroke_id,
                    "semantic_role": role["semantic_role"],
                }
            )
        return True

    def _append_mask_stroke(self, points, radius, operation, semantic_role, stroke_id):
        radius_pixel = self._preview_transform.target_radius_to_original(radius, normalized=True)
        side = self.project.front_relief
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
                    "semantic_role": semantic_role,
                }
            )

    def undo_last_correction(self):
        if self.project is None:
            return
        groups = [marker for marker in self.project.manual_markers if marker.marker_type == "semantic_stroke_group"]
        if not groups:
            return super().undo_last_correction()
        group = groups[-1]
        stroke_id = group.data.get("stroke_id")
        side = self.project.front_relief
        side.lineart_region_overrides = [
            item for item in side.lineart_region_overrides if item.get("stroke_id") != stroke_id
        ]
        side.mask_edits = [item for item in side.mask_edits if item.get("stroke_id") != stroke_id]
        side.region_layers = [item for item in side.region_layers if item.get("stroke_id") != stroke_id]
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
        groups = [marker for marker in self.project.manual_markers if marker.marker_type == "semantic_stroke_group"]
        counts = {role: 0 for role in ROLE_LABELS}
        locked_count = 0
        for marker in groups:
            role = marker.data.get("role")
            if role in counts:
                counts[role] += 1
            if bool(marker.data.get("locked", False)):
                locked_count += 1
        level_count = sum(counts[key] for key in ("level_base", "level_low", "level_mid", "level_high", "level_top"))
        self.correction_label.setText(
            "人工标注："
            f"空 {counts['background']}　层级 {level_count}　"
            f"抬高 {counts['raise']}　压低 {counts['recess']}　锁定 {locked_count}"
        )

    def _update_correction_count(self):
        self._update_semantic_count()

    # ----------------------------------------------------------- guided review
    def _refresh_review_image(self, *_):
        mode = REVIEW_OPTIONS.get(self.review_combo.currentText(), "regions")
        if mode == "uncertainty":
            path = self._preview_paths.get("uncertainty_preview")
        elif mode == "mask":
            path = self._preview_paths.get("mask_overlay_preview") or self._preview_paths.get("mask_preview")
        else:
            path = self._preview_paths.get("lineart_region_preview") or self._preview_paths.get("mask_overlay_preview")
        if path:
            self.region_preview.set_image(path)

    def focus_next_issue(self):
        if not self._review_regions:
            self.statusBar().showMessage("当前没有待确认的主要区域。")
            return
        base = self._preview_paths.get("lineart_region_preview")
        if not base:
            self.statusBar().showMessage("当前图片未生成可编号的线稿区域。请使用置信度热图检查边缘。")
            return
        self._review_region_index = (self._review_region_index + 1) % len(self._review_regions)
        region = self._review_regions[self._review_region_index]
        output = Path(base).with_name("focused_region_preview.png")
        focused = save_focused_region_preview(base, region, output)
        self.region_preview.set_image(focused)
        self.review_combo.setCurrentText("区域语义图")
        self.statusBar().showMessage(
            f"待确认区域 #{region.get('display_id', '?')}，面积 {region.get('pixel_count', 0)} 像素。"
        )

    # ----------------------------------------------------------- preview/profile
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
        prepared, _ = payload
        self._prepared_preview = prepared
        self._preview_paths = dict(prepared.report.get("preview_paths", {}))
        super()._preview_ready(payload)
        region_report = prepared.report.get("lineart_region_graph", {})
        lineart_labels = None
        if prepared.report.get("artwork_interpretation") == "lineart":
            lineart_labels, region_report = analyze_lineart_regions(prepared.rgba, prepared.mask)
        uncertainty_map, uncertainty = build_uncertainty_map(
            prepared.rgba,
            prepared.mask,
            lineart_labels=lineart_labels,
            lineart_report=region_report,
            override_report=prepared.report.get("lineart_region_overrides", {}),
        )
        preview_dir = asset_root_for(self.project_path) / "previews" / "semantic_studio"
        self._preview_paths["uncertainty_preview"] = save_uncertainty_preview(
            prepared.rgba,
            uncertainty_map,
            preview_dir / "uncertainty_preview.png",
            uncertainty,
        )
        resolved_ids = {
            int(item.get("region_id", -1))
            for item in prepared.report.get("lineart_region_overrides", {}).get("applied", [])
            if isinstance(item, dict)
        }
        self._review_regions = [
            item for item in region_report.get("regions", []) if int(item.get("region_id", -1)) not in resolved_ids
        ]
        self._review_region_index = -1
        self._update_semantic_count()
        self._refresh_review_image()
        self._refresh_profile_preview()
        self.summary_box.append(
            "\n边缘处理：窄带轮廓净化 + 有符号距离场重采样。\n"
            f"高疑点占比：{float(uncertainty.get('high_uncertainty_fraction', 0.0)) * 100.0:.1f}%"
        )

    def _refresh_profile_preview(self, *_):
        if self._prepared_preview is None or self.project is None or not self.project_path:
            return
        orientation = "horizontal" if self.section_orientation_combo.currentIndex() == 0 else "vertical"
        profile = sample_height_profile(
            self._prepared_preview.heightmap,
            self._prepared_preview.mask,
            orientation=orientation,
            position_normalized=float(self.section_position_spin.value()) / 100.0,
            width_mm=float(self.project.dimensions.width_mm),
            height_mm=float(self.project.dimensions.height_mm),
            relief_height_mm=float(self.project.front_relief.relief_height_mm),
        )
        preview_dir = asset_root_for(self.project_path) / "previews" / "semantic_studio"
        output = save_height_profile_preview(profile, preview_dir / "height_profile_preview.png")
        self.section_preview.set_image(output)

    # ----------------------------------------------------------- export
    def export_heightmap(self):
        if self.project is None or not self.project_path or QFileDialog is None:
            return
        default = Path(self.output_directory or Path(self.project_path).parent) / f"{self.project.name}.glb"
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "导出 Blender 模型",
            str(default),
            "Blender GLB 模型 (*.glb)",
        )
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
            "人工语义、绝对层级和锁定区域已经进入实体蒙版与高度场。"
        )
        self.statusBar().showMessage("GLB 已导出，可直接拖入 Blender。")
        if QMessageBox is not None:
            QMessageBox.information(self, APP_TITLE, f"模型导出完成：\n{path}")

    def show_phase_information(self):
        if QMessageBox is not None:
            QMessageBox.information(
                self,
                "人工标注说明",
                "先用部件或笔刷把区域标成空、固定高度层级、相对抬高或相对压低。\n\n"
                "再用置信度热图和高度剖面检查边缘与Z轴关系，确认后直接导出GLB。",
            )
