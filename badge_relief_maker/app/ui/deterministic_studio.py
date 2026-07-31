"""Simple deterministic three-stage grayscale relief desktop workflow.

The default window intentionally depends only on the approved-mask/height core
and the regular-grid mesh builder. Advanced semantic, Bezier and adaptive tools
are opened explicitly and never modify this window's approved artifacts in the
background.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover - core-only installations
    Qt = None
    Signal = None
    QImage = None
    QPixmap = None
    QApplication = None
    QCheckBox = None
    QComboBox = None
    QDoubleSpinBox = None
    QFileDialog = None
    QFormLayout = None
    QFrame = None
    QGridLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QMainWindow = object
    QMessageBox = None
    QPushButton = None
    QScrollArea = None
    QSpinBox = None
    QSplitter = None
    QTextEdit = None
    QVBoxLayout = None
    QWidget = object

from ..core.approved_heightmap_builder import build_relief_from_approved_heightmap
from ..core.deterministic_workflow import (
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


APP_TITLE = "确定性灰度浮雕生成器"
APP_SUBTITLE = "实体蒙版 → 高度主图 → 规则网格；原图在确认后不再参与网格构建"
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
SOLID_EDIT_OPTIONS = {
    "背景取样": "sample_background",
    "增加实体": "add",
    "删除实体": "remove",
    "填充封闭区域": "fill",
    "删除连通组件": "delete_component",
}
HEIGHT_EDIT_OPTIONS = {
    "最低": ("set", 0.00),
    "低": ("set", 0.25),
    "中": ("set", 0.50),
    "高": ("set", 0.75),
    "最高": ("set", 1.00),
    "局部抬高": ("add", None),
    "局部压低": ("subtract", None),
    "局部平滑": ("smooth", None),
}
SHAPE_OPTIONS = {"圆形画笔": "circle", "矩形选择": "rectangle", "多边形选择": "polygon"}


if Signal is not None:

    class _PreviewPanel(QLabel):
        clicked = Signal(float, float)

        def __init__(self, title: str, *, interactive: bool = False):
            super().__init__()
            self.title = str(title)
            self.interactive = bool(interactive)
            self._source_pixmap = None
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setMinimumSize(250, 230)
            self.setFrameShape(QFrame.Shape.StyledPanel)
            self.setText(self.title)
            self.setStyleSheet(
                "QLabel { background:#15191f; color:#a8b2bf; border:1px solid #343c48; border-radius:7px; padding:6px; }"
            )

        def set_array(self, array: np.ndarray):
            values = np.asarray(array)
            if values.ndim == 2:
                gray = np.ascontiguousarray(values.astype(np.uint8))
                image = QImage(gray.data, gray.shape[1], gray.shape[0], gray.strides[0], QImage.Format.Format_Grayscale8).copy()
            elif values.ndim == 3 and values.shape[2] in {3, 4}:
                pixels = np.ascontiguousarray(values.astype(np.uint8))
                fmt = QImage.Format.Format_RGB888 if pixels.shape[2] == 3 else QImage.Format.Format_RGBA8888
                image = QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0], fmt).copy()
            else:
                self.setText(f"{self.title}\n无法显示")
                return
            self._source_pixmap = QPixmap.fromImage(image)
            self._refresh_pixmap()

        def clear_array(self, message: str | None = None):
            self._source_pixmap = None
            self.clear()
            self.setText(message or self.title)

        def _display_rect(self):
            if self._source_pixmap is None or self._source_pixmap.isNull():
                return None
            size = self._source_pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            left = (self.width() - size.width()) / 2.0
            top = (self.height() - size.height()) / 2.0
            return left, top, float(size.width()), float(size.height())

        def _refresh_pixmap(self):
            if self._source_pixmap is None:
                return
            self.setPixmap(
                self._source_pixmap.scaled(
                    self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )

        def resizeEvent(self, event):
            self._refresh_pixmap()
            super().resizeEvent(event)

        def mousePressEvent(self, event):
            if self.interactive:
                rect = self._display_rect()
                if rect is not None:
                    left, top, width, height = rect
                    x = float(event.position().x())
                    y = float(event.position().y())
                    if left <= x <= left + width and top <= y <= top + height:
                        self.clicked.emit((x - left) / max(width, 1.0), (y - top) / max(height, 1.0))
            super().mousePressEvent(event)

else:
    _PreviewPanel = None


class MainWindow(QMainWindow):
    """Default GUI for approved mask and height-master production."""

    def __init__(self):
        super().__init__()
        self.source_path: Path | None = None
        self.source_data = None
        self.solid_draft: SolidMaskDraft | None = None
        self.height_draft: HeightMasterDraft | None = None
        self.solid_edits: list[dict] = []
        self.solid_redo: list[dict] = []
        self.height_edits: list[dict] = []
        self.height_redo: list[dict] = []
        self.background_samples: list[dict] = []
        self.solid_polygon_points: list[list[float]] = []
        self.height_polygon_points: list[list[float]] = []
        self.solid_mask_confirmed = False
        self.height_master_confirmed = False
        self.artifact_directory: Path | None = None
        self._advanced_window = None
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="badge-relief-deterministic-")

        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 900)
        self.setMinimumSize(1100, 700)
        self._build_ui()
        self._connect_signals()
        self._update_stage_state()

    # ------------------------------------------------------------------ setup
    def _build_ui(self):
        if QWidget is None:
            return
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(APP_TITLE)
        title.setStyleSheet("font-size:22px; font-weight:700;")
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#667085;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box, 1)
        self.import_button = QPushButton("导入图片")
        self.open_project_button = QPushButton("打开项目")
        self.save_artifacts_button = QPushButton("保存主图与项目")
        self.advanced_button = QPushButton("高级功能…")
        heading.addWidget(self.import_button)
        heading.addWidget(self.open_project_button)
        heading.addWidget(self.save_artifacts_button)
        heading.addWidget(self.advanced_button)
        root.addLayout(heading)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumWidth(320)
        controls_scroll.setMaximumWidth(430)
        controls_root = QWidget()
        controls = QVBoxLayout(controls_root)
        controls.setContentsMargins(4, 4, 8, 4)
        controls.setSpacing(8)

        # Stage one
        self.solid_group = QGroupBox("第一步：确定哪里有材料")
        solid_layout = QVBoxLayout(self.solid_group)
        solid_form = QFormLayout()
        self.solid_mode_combo = QComboBox()
        self.solid_mode_combo.addItems(SOLID_MODE_OPTIONS)
        self.solid_mode_combo.setCurrentText("自动去背景")
        self.explicit_background_combo = QComboBox()
        self.explicit_background_combo.addItems(["自动判断边缘背景", "亮背景", "暗背景"])
        self.background_tolerance_spin = self._double_spin(0.0, 1.0, 0.08, 0.01, 3)
        self.solid_edit_combo = QComboBox()
        self.solid_edit_combo.addItems(SOLID_EDIT_OPTIONS)
        self.solid_shape_combo = QComboBox()
        self.solid_shape_combo.addItems(SHAPE_OPTIONS)
        self.solid_radius_spin = self._double_spin(0.002, 0.5, 0.04, 0.005, 3)
        solid_form.addRow("实体模式", self.solid_mode_combo)
        solid_form.addRow("背景模式", self.explicit_background_combo)
        solid_form.addRow("背景容差", self.background_tolerance_spin)
        solid_form.addRow("点击操作", self.solid_edit_combo)
        solid_form.addRow("选择形状", self.solid_shape_combo)
        solid_form.addRow("画笔/区域大小", self.solid_radius_spin)
        solid_layout.addLayout(solid_form)
        solid_buttons = QHBoxLayout()
        self.refresh_solid_button = QPushButton("生成实体初稿")
        self.undo_solid_button = QPushButton("撤销")
        self.redo_solid_button = QPushButton("重做")
        solid_buttons.addWidget(self.refresh_solid_button)
        solid_buttons.addWidget(self.undo_solid_button)
        solid_buttons.addWidget(self.redo_solid_button)
        solid_layout.addLayout(solid_buttons)
        polygon_buttons = QHBoxLayout()
        self.finish_solid_polygon_button = QPushButton("完成多边形")
        self.cancel_solid_polygon_button = QPushButton("取消多边形")
        polygon_buttons.addWidget(self.finish_solid_polygon_button)
        polygon_buttons.addWidget(self.cancel_solid_polygon_button)
        solid_layout.addLayout(polygon_buttons)
        self.confirm_solid_button = QPushButton("确认并锁定实体蒙版")
        self.unlock_solid_button = QPushButton("返回修改实体")
        solid_layout.addWidget(self.confirm_solid_button)
        solid_layout.addWidget(self.unlock_solid_button)
        self.solid_status_label = QLabel("尚未确认实体蒙版")
        self.solid_status_label.setWordWrap(True)
        solid_layout.addWidget(self.solid_status_label)
        controls.addWidget(self.solid_group)

        # Stage two
        self.height_group = QGroupBox("第二步：确定实体内部高度")
        height_layout = QVBoxLayout(self.height_group)
        height_form = QFormLayout()
        self.height_mode_combo = QComboBox()
        self.height_mode_combo.addItems(HEIGHT_MODE_OPTIONS)
        self.low_percentile_spin = self._double_spin(0.0, 49.9, 2.0, 0.5, 1)
        self.high_percentile_spin = self._double_spin(50.1, 100.0, 98.0, 0.5, 1)
        self.black_point_spin = self._double_spin(0.0, 0.99, 0.0, 0.01, 2)
        self.white_point_spin = self._double_spin(0.01, 1.0, 1.0, 0.01, 2)
        self.midtone_spin = self._double_spin(0.1, 4.0, 1.0, 0.05, 2)
        self.invert_check = QCheckBox("反转")
        self.fixed_height_spin = self._double_spin(0.0, 1.0, 1.0, 0.05, 2)
        self.line_depth_spin = self._double_spin(0.0, 5.0, 0.2, 0.05, 2, " mm")
        self.line_threshold_spin = self._double_spin(0.0, 1.0, 0.35, 0.01, 2)
        self.line_softness_spin = self._double_spin(0.0, 8.0, 0.75, 0.25, 2, " px")
        self.height_edit_combo = QComboBox()
        self.height_edit_combo.addItems(HEIGHT_EDIT_OPTIONS)
        self.height_shape_combo = QComboBox()
        self.height_shape_combo.addItems(SHAPE_OPTIONS)
        self.height_radius_spin = self._double_spin(0.002, 0.5, 0.04, 0.005, 3)
        self.height_amount_spin = self._double_spin(0.0, 1.0, 0.10, 0.01, 2)
        height_form.addRow("高度解释", self.height_mode_combo)
        height_form.addRow("最低点百分位", self.low_percentile_spin)
        height_form.addRow("最高点百分位", self.high_percentile_spin)
        height_form.addRow("最低点", self.black_point_spin)
        height_form.addRow("最高点", self.white_point_spin)
        height_form.addRow("中间调", self.midtone_spin)
        height_form.addRow("方向", self.invert_check)
        height_form.addRow("固定高度", self.fixed_height_spin)
        height_form.addRow("线条凹凸深度", self.line_depth_spin)
        height_form.addRow("线条阈值", self.line_threshold_spin)
        height_form.addRow("线条边缘平滑", self.line_softness_spin)
        height_form.addRow("高度画笔", self.height_edit_combo)
        height_form.addRow("选择形状", self.height_shape_combo)
        height_form.addRow("画笔/区域大小", self.height_radius_spin)
        height_form.addRow("抬高/压低/平滑量", self.height_amount_spin)
        height_layout.addLayout(height_form)
        height_buttons = QHBoxLayout()
        self.refresh_height_button = QPushButton("生成高度初稿")
        self.reset_height_button = QPushButton("重置高度参数")
        height_buttons.addWidget(self.refresh_height_button)
        height_buttons.addWidget(self.reset_height_button)
        height_layout.addLayout(height_buttons)
        edit_buttons = QHBoxLayout()
        self.undo_height_button = QPushButton("撤销")
        self.redo_height_button = QPushButton("重做")
        self.finish_height_polygon_button = QPushButton("完成多边形")
        edit_buttons.addWidget(self.undo_height_button)
        edit_buttons.addWidget(self.redo_height_button)
        edit_buttons.addWidget(self.finish_height_polygon_button)
        height_layout.addLayout(edit_buttons)
        self.confirm_height_button = QPushButton("确认并锁定高度主图")
        self.unlock_height_button = QPushButton("返回修改高度")
        height_layout.addWidget(self.confirm_height_button)
        height_layout.addWidget(self.unlock_height_button)
        self.height_status_label = QLabel("尚未确认高度主图")
        self.height_status_label.setWordWrap(True)
        height_layout.addWidget(self.height_status_label)
        controls.addWidget(self.height_group)

        # Stage three
        self.output_group = QGroupBox("第三步：规则网格构建与导出")
        output_layout = QVBoxLayout(self.output_group)
        output_form = QFormLayout()
        self.width_spin = self._double_spin(1.0, 2000.0, 80.0, 1.0, 2, " mm")
        self.height_spin = self._double_spin(1.0, 2000.0, 80.0, 1.0, 2, " mm")
        self.base_spin = self._double_spin(0.0, 100.0, 2.0, 0.1, 2, " mm")
        self.relief_spin = self._double_spin(0.0, 100.0, 3.0, 0.1, 2, " mm")
        self.minimum_thickness_spin = self._double_spin(0.0, 100.0, 0.8, 0.1, 2, " mm")
        self.min_feature_spin = self._double_spin(0.001, 100.0, 0.3, 0.05, 3, " mm")
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(QUALITY_OPTIONS)
        self.quality_combo.setCurrentText("标准")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["OBJ", "STL", "GLB"])
        output_form.addRow("宽度", self.width_spin)
        output_form.addRow("高度", self.height_spin)
        output_form.addRow("基础厚度", self.base_spin)
        output_form.addRow("浮雕高度", self.relief_spin)
        output_form.addRow("最小厚度警告", self.minimum_thickness_spin)
        output_form.addRow("希望保留的最小特征", self.min_feature_spin)
        output_form.addRow("质量档位", self.quality_combo)
        output_form.addRow("导出格式", self.format_combo)
        output_layout.addLayout(output_form)
        self.build_button = QPushButton("构建并导出")
        self.build_button.setMinimumHeight(42)
        output_layout.addWidget(self.build_button)
        self.output_status_label = QLabel("需要先确认实体蒙版和高度主图")
        self.output_status_label.setWordWrap(True)
        output_layout.addWidget(self.output_status_label)
        controls.addWidget(self.output_group)
        controls.addStretch(1)
        controls_scroll.setWidget(controls_root)
        splitter.addWidget(controls_scroll)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        preview_grid = QGridLayout()
        self.source_preview = _PreviewPanel("原图（仅参考）", interactive=True)
        self.solid_preview = _PreviewPanel("实体蒙版", interactive=True)
        self.height_preview = _PreviewPanel("高度主图", interactive=True)
        self.mesh_preview = _PreviewPanel("三维明暗预览", interactive=False)
        preview_grid.addWidget(self.source_preview, 0, 0)
        preview_grid.addWidget(self.solid_preview, 0, 1)
        preview_grid.addWidget(self.height_preview, 1, 0)
        preview_grid.addWidget(self.mesh_preview, 1, 1)
        right_layout.addLayout(preview_grid, 1)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(110)
        right_layout.addWidget(self.log_box)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("导入图片后，先确认实体范围。")

    def _double_spin(self, minimum, maximum, value, step, decimals, suffix=""):
        spin = QDoubleSpinBox()
        spin.setRange(float(minimum), float(maximum))
        spin.setValue(float(value))
        spin.setSingleStep(float(step))
        spin.setDecimals(int(decimals))
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _connect_signals(self):
        self.import_button.clicked.connect(self.import_image)
        self.open_project_button.clicked.connect(self.open_project)
        self.save_artifacts_button.clicked.connect(self.save_artifacts)
        self.advanced_button.clicked.connect(self.open_advanced)
        self.refresh_solid_button.clicked.connect(self.refresh_solid)
        self.undo_solid_button.clicked.connect(self.undo_solid)
        self.redo_solid_button.clicked.connect(self.redo_solid)
        self.finish_solid_polygon_button.clicked.connect(self.finish_solid_polygon)
        self.cancel_solid_polygon_button.clicked.connect(self.cancel_solid_polygon)
        self.confirm_solid_button.clicked.connect(self.confirm_solid)
        self.unlock_solid_button.clicked.connect(self.unlock_solid)
        self.refresh_height_button.clicked.connect(self.refresh_height)
        self.reset_height_button.clicked.connect(self.reset_height_controls)
        self.undo_height_button.clicked.connect(self.undo_height)
        self.redo_height_button.clicked.connect(self.redo_height)
        self.finish_height_polygon_button.clicked.connect(self.finish_height_polygon)
        self.confirm_height_button.clicked.connect(self.confirm_height)
        self.unlock_height_button.clicked.connect(self.unlock_height)
        self.build_button.clicked.connect(self.build_and_export)
        self.source_preview.clicked.connect(self._source_clicked)
        self.solid_preview.clicked.connect(self._solid_clicked)
        self.height_preview.clicked.connect(self._height_clicked)
        self.solid_mode_combo.currentTextChanged.connect(self._solid_controls_changed)
        self.explicit_background_combo.currentTextChanged.connect(self._solid_controls_changed)
        self.background_tolerance_spin.valueChanged.connect(self._solid_controls_changed)
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
            signal = control.currentTextChanged if isinstance(control, QComboBox) else (
                control.toggled if isinstance(control, QCheckBox) else control.valueChanged
            )
            signal.connect(self._height_controls_changed)

    # --------------------------------------------------------------- state/UI
    def _log(self, message: str, payload: dict | None = None):
        text = str(message)
        if payload is not None:
            text += "\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        self.log_box.setPlainText(text)
        self.statusBar().showMessage(str(message).splitlines()[0])

    def _show_error(self, title: str, error):
        self._log(f"{title}：{error}")
        if QMessageBox is not None:
            QMessageBox.critical(self, title, str(error))

    def _update_stage_state(self):
        has_source = self.source_data is not None
        solid_locked = self.solid_mask_confirmed
        height_locked = self.height_master_confirmed
        self.save_artifacts_button.setEnabled(has_source and self.solid_draft is not None and self.height_draft is not None)
        for widget in (
            self.solid_mode_combo,
            self.explicit_background_combo,
            self.background_tolerance_spin,
            self.solid_edit_combo,
            self.solid_shape_combo,
            self.solid_radius_spin,
            self.refresh_solid_button,
            self.undo_solid_button,
            self.redo_solid_button,
            self.finish_solid_polygon_button,
            self.cancel_solid_polygon_button,
        ):
            widget.setEnabled(has_source and not solid_locked)
        self.confirm_solid_button.setEnabled(has_source and self.solid_draft is not None and not solid_locked)
        self.unlock_solid_button.setEnabled(solid_locked)
        self.solid_status_label.setText("实体蒙版：已确认并锁定" if solid_locked else "实体蒙版：需要修正并确认")

        height_ready = has_source and solid_locked
        for widget in (
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
            self.height_edit_combo,
            self.height_shape_combo,
            self.height_radius_spin,
            self.height_amount_spin,
            self.refresh_height_button,
            self.reset_height_button,
            self.undo_height_button,
            self.redo_height_button,
            self.finish_height_polygon_button,
        ):
            widget.setEnabled(height_ready and not height_locked)
        self.confirm_height_button.setEnabled(height_ready and self.height_draft is not None and not height_locked)
        self.unlock_height_button.setEnabled(height_locked)
        self.height_status_label.setText("高度主图：已确认并锁定" if height_locked else "高度主图：需要选择解释方式、修正并确认")

        can_build = solid_locked and height_locked and self.artifact_directory is not None
        self.build_button.setEnabled(can_build)
        self.output_status_label.setText(
            "已批准主图就绪；网格只读取 solid_mask 与 height_master。" if can_build else "需要先确认实体蒙版和高度主图"
        )

    def _solid_controls_changed(self, *_):
        if self.source_data is not None and not self.solid_mask_confirmed:
            self.refresh_solid()

    def _height_controls_changed(self, *_):
        if self.solid_mask_confirmed and not self.height_master_confirmed:
            self.refresh_height()

    # --------------------------------------------------------------- import
    def import_image(self):
        if QFileDialog is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if path:
            self.load_image(path)

    def open_project(self):
        if QFileDialog is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开确定性浮雕项目", "", "Project (project.json *.json)")
        if path:
            self.load_project(path)

    def load_project(self, project_path: str | Path):
        try:
            loaded = load_workflow_artifacts(project_path, verify_hashes=True)
            project = loaded.project
            self.source_data = loaded.source
            original = project.get("source_path")
            self.source_path = Path(original).resolve() if original and Path(original).exists() else Path(project_path).resolve().parent / "source_aligned.png"
            self.artifact_directory = Path(project_path).resolve().parent
            self.solid_edits = [dict(item) for item in project.get("solid_mask_edits", ()) if isinstance(item, dict)]
            self.height_edits = [dict(item) for item in project.get("height_edits", ()) if isinstance(item, dict)]
            self.solid_redo.clear()
            self.height_redo.clear()
            self.background_samples.clear()
            self.solid_polygon_points.clear()
            self.height_polygon_points.clear()
            self.solid_draft = SolidMaskDraft(
                mask=loaded.solid_mask,
                report=dict(project.get("solid_mask_report", {})),
            )
            self.height_draft = HeightMasterDraft(
                height_master=loaded.height_master,
                line_mask=np.zeros_like(loaded.solid_mask),
                report=dict(project.get("height_master_report", {})),
            )
            self.solid_mask_confirmed = bool(project.get("solid_mask_confirmed"))
            self.height_master_confirmed = bool(project.get("height_master_confirmed"))
            parameters = project.get("source_parameters", {})
            solid_mode = str(parameters.get("solid_mode", "auto_background"))
            height_mode = str(parameters.get("height_mode", "bright_high"))
            self.background_samples = [
                dict(item) for item in parameters.get("background_samples", ()) if isinstance(item, dict)
            ]
            for label, value in SOLID_MODE_OPTIONS.items():
                if value == solid_mode:
                    self.solid_mode_combo.setCurrentText(label)
                    break
            for label, value in HEIGHT_MODE_OPTIONS.items():
                if value == height_mode:
                    self.height_mode_combo.setCurrentText(label)
                    break
            normalization = parameters.get("normalization", {})
            self.low_percentile_spin.setValue(float(normalization.get("low_percentile", 2.0)))
            self.high_percentile_spin.setValue(float(normalization.get("high_percentile", 98.0)))
            self.black_point_spin.setValue(float(normalization.get("black_point", 0.0)))
            self.white_point_spin.setValue(float(normalization.get("white_point", 1.0)))
            self.midtone_spin.setValue(float(normalization.get("midtone", 1.0)))
            self.invert_check.setChecked(bool(normalization.get("invert", False)))
            solid_settings = parameters.get("solid_settings", {})
            explicit_background = str(solid_settings.get("explicit_background", ""))
            self.explicit_background_combo.setCurrentText(
                "亮背景" if explicit_background == "bright" else "暗背景" if explicit_background == "dark" else "自动判断边缘背景"
            )
            self.background_tolerance_spin.setValue(float(solid_settings.get("background_tolerance", 0.08)))
            height_settings = parameters.get("height_settings", {})
            self.fixed_height_spin.setValue(float(height_settings.get("fixed_height", 1.0)))
            self.line_depth_spin.setValue(float(height_settings.get("line_depth_mm", 0.2)))
            self.line_threshold_spin.setValue(float(height_settings.get("line_threshold", 0.35)))
            self.line_softness_spin.setValue(float(height_settings.get("line_softness_px", 0.75)))
            mesh_settings = parameters.get("mesh_settings", {})
            self.width_spin.setValue(float(mesh_settings.get("width_mm", 80.0)))
            self.height_spin.setValue(float(mesh_settings.get("height_mm", 80.0)))
            self.base_spin.setValue(float(mesh_settings.get("base_thickness_mm", 2.0)))
            self.relief_spin.setValue(float(mesh_settings.get("relief_height_mm", 3.0)))
            self.minimum_thickness_spin.setValue(float(mesh_settings.get("minimum_thickness_mm", 0.8)))
            self.min_feature_spin.setValue(float(mesh_settings.get("minimum_feature_mm", 0.3)))
            quality_value = str(mesh_settings.get("quality_mode", "standard"))
            for label, value in QUALITY_OPTIONS.items():
                if value == quality_value:
                    self.quality_combo.setCurrentText(label)
                    break
            export_format = str(mesh_settings.get("export_format", "obj")).upper()
            if export_format in {"OBJ", "STL", "GLB"}:
                self.format_combo.setCurrentText(export_format)
            self.source_preview.set_array(self.source_data.rgba8)
            self.solid_preview.set_array(loaded.solid_mask.astype(np.uint8) * 255)
            self.height_preview.set_array(np.round(loaded.height_master * 255.0).astype(np.uint8))
            self.mesh_preview.set_array(self._shaded_preview(loaded.height_master, loaded.solid_mask))
            self._update_stage_state()
            self._log(
                "项目已按保存的批准主图重新打开；已验证保存文件哈希。",
                {
                    "project": str(Path(project_path).resolve()),
                    "solid_mask_confirmed": self.solid_mask_confirmed,
                    "height_master_confirmed": self.height_master_confirmed,
                    "height_edit_count": len(self.height_edits),
                    "solid_edit_count": len(self.solid_edits),
                },
            )
        except Exception as exc:
            self._show_error("打开项目失败", exc)

    def load_image(self, path: str | Path):
        try:
            self.source_path = Path(path).resolve()
            self.source_data = load_source_image(self.source_path)
        except Exception as exc:
            self._show_error("导入失败", exc)
            return
        self.solid_edits.clear()
        self.solid_redo.clear()
        self.height_edits.clear()
        self.height_redo.clear()
        self.background_samples.clear()
        self.solid_polygon_points.clear()
        self.height_polygon_points.clear()
        self.solid_mask_confirmed = False
        self.height_master_confirmed = False
        self.artifact_directory = self.source_path.parent / f"{self.source_path.stem}_relief_project"
        self.source_preview.set_array(self.source_data.rgba8)
        self.solid_preview.clear_array("实体蒙版\n等待生成")
        self.height_preview.clear_array("高度主图\n先确认实体")
        self.mesh_preview.clear_array("三维明暗预览\n先确认高度")
        self.refresh_solid()
        self._log(
            "图片已导入。白色既可能是背景，也可能是实体；请先选择实体模式并确认。",
            {"path": str(self.source_path), "mode": self.source_data.source_mode, "dtype": self.source_data.source_dtype},
        )

    # --------------------------------------------------------------- solid
    def _explicit_background(self):
        text = self.explicit_background_combo.currentText()
        return "bright" if text == "亮背景" else "dark" if text == "暗背景" else None

    def refresh_solid(self):
        if self.source_data is None:
            return
        try:
            self.solid_draft = draft_solid_mask(
                self.source_data,
                mode=SOLID_MODE_OPTIONS[self.solid_mode_combo.currentText()],
                background_samples=self.background_samples,
                background_tolerance=float(self.background_tolerance_spin.value()),
                explicit_background=self._explicit_background(),
                explicit_threshold=0.9 if self._explicit_background() == "bright" else 0.1,
                edits=self.solid_edits,
            )
            self.solid_preview.set_array(self.solid_draft.mask.astype(np.uint8) * 255)
            self.solid_mask_confirmed = False
            self.height_master_confirmed = False
            self.height_draft = None
            self.height_preview.clear_array("高度主图\n实体变化后需要重新生成")
            self.mesh_preview.clear_array("三维明暗预览\n高度尚未确认")
            self._update_stage_state()
        except Exception as exc:
            self._show_error("实体蒙版生成失败", exc)

    def _source_clicked(self, x: float, y: float):
        if self.solid_mask_confirmed or self.source_data is None:
            return
        if SOLID_EDIT_OPTIONS[self.solid_edit_combo.currentText()] == "sample_background":
            self.background_samples.append({"x": float(x), "y": float(y), "coordinate_space": "normalized"})
            self.solid_mode_combo.setCurrentText("自动去背景")
            self.refresh_solid()
            self._log(f"已添加背景采样点：x={x:.3f}, y={y:.3f}")
        else:
            self._apply_solid_click(x, y)

    def _solid_clicked(self, x: float, y: float):
        if not self.solid_mask_confirmed:
            self._apply_solid_click(x, y)

    def _apply_solid_click(self, x: float, y: float):
        operation = SOLID_EDIT_OPTIONS[self.solid_edit_combo.currentText()]
        if operation == "sample_background":
            self.background_samples.append({"x": float(x), "y": float(y), "coordinate_space": "normalized"})
            self.refresh_solid()
            return
        shape = SHAPE_OPTIONS[self.solid_shape_combo.currentText()]
        if shape == "polygon":
            self.solid_polygon_points.append([float(x), float(y)])
            self._log(f"实体多边形已记录 {len(self.solid_polygon_points)} 个点；至少 3 点后点击“完成多边形”。")
            return
        edit = {
            "operation": operation,
            "shape": shape,
            "x": float(x),
            "y": float(y),
            "coordinate_space": "normalized",
            "radius_normalized": float(self.solid_radius_spin.value()),
            "width_normalized": float(self.solid_radius_spin.value()) * 2.0,
            "height_normalized": float(self.solid_radius_spin.value()) * 2.0,
        }
        self.solid_edits.append(edit)
        self.solid_redo.clear()
        self.solid_mode_combo.setCurrentText("自定义实体范围")
        self.refresh_solid()

    def finish_solid_polygon(self):
        if len(self.solid_polygon_points) < 3:
            self._log("实体多边形至少需要 3 个点。")
            return
        operation = SOLID_EDIT_OPTIONS[self.solid_edit_combo.currentText()]
        if operation in {"sample_background", "fill", "delete_component"}:
            operation = "add" if operation == "sample_background" else operation
        self.solid_edits.append(
            {
                "operation": operation,
                "shape": "polygon",
                "points": [list(point) for point in self.solid_polygon_points],
                "coordinate_space": "normalized",
            }
        )
        self.solid_polygon_points.clear()
        self.solid_redo.clear()
        self.solid_mode_combo.setCurrentText("自定义实体范围")
        self.refresh_solid()

    def cancel_solid_polygon(self):
        self.solid_polygon_points.clear()
        self._log("已取消当前实体多边形。")

    def undo_solid(self):
        if self.solid_edits:
            self.solid_redo.append(self.solid_edits.pop())
            self.refresh_solid()
        elif self.background_samples:
            self.background_samples.pop()
            self.refresh_solid()

    def redo_solid(self):
        if self.solid_redo:
            self.solid_edits.append(self.solid_redo.pop())
            self.refresh_solid()

    def confirm_solid(self):
        self.refresh_solid()
        if self.solid_draft is None or not self.solid_draft.mask.any():
            self._show_error("无法确认实体", "实体蒙版为空。")
            return
        self.solid_mask_confirmed = True
        self.refresh_height()
        self._update_stage_state()
        self._log("实体蒙版已确认并锁定。后续高度处理不会改变实体范围。", self.solid_draft.report)

    def unlock_solid(self):
        self.solid_mask_confirmed = False
        self.height_master_confirmed = False
        self.artifact_directory = self.source_path.parent / f"{self.source_path.stem}_relief_project" if self.source_path else None
        self._update_stage_state()
        self._log("已主动返回实体阶段；高度确认同时取消。")

    # --------------------------------------------------------------- height
    def _height_arguments(self):
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
            "height_edits": tuple(self.height_edits),
        }

    def refresh_height(self):
        if self.source_data is None or self.solid_draft is None or not self.solid_mask_confirmed:
            return
        try:
            self.height_draft = draft_height_master(self.source_data, self.solid_draft.mask, **self._height_arguments())
            preview = np.round(self.height_draft.height_master * 255.0).astype(np.uint8)
            self.height_preview.set_array(preview)
            self.mesh_preview.set_array(self._shaded_preview(self.height_draft.height_master, self.solid_draft.mask))
            self.height_master_confirmed = False
            self._update_stage_state()
        except Exception as exc:
            self._show_error("高度主图生成失败", exc)

    @staticmethod
    def _shaded_preview(height, mask):
        values = np.asarray(height, dtype=np.float32)
        if min(values.shape) < 2:
            return np.round(values * 255).astype(np.uint8)
        dy, dx = np.gradient(values)
        nx, ny, nz = -dx, -dy, np.ones_like(values) * 0.6
        norm = np.maximum(np.sqrt(nx * nx + ny * ny + nz * nz), 1e-8)
        light = np.asarray([-0.4, -0.5, 0.75], dtype=np.float32)
        light /= np.linalg.norm(light)
        shade = np.clip(nx / norm * light[0] + ny / norm * light[1] + nz / norm * light[2], 0, 1)
        return np.round(np.where(mask, 0.2 + 0.8 * shade, 0.0) * 255).astype(np.uint8)

    def _height_clicked(self, x: float, y: float):
        if self.height_master_confirmed or not self.solid_mask_confirmed:
            return
        shape = SHAPE_OPTIONS[self.height_shape_combo.currentText()]
        if shape == "polygon":
            self.height_polygon_points.append([float(x), float(y)])
            self._log(f"高度多边形已记录 {len(self.height_polygon_points)} 个点；至少 3 点后点击“完成多边形”。")
            return
        self.height_edits.append(self._height_edit(shape, x, y))
        self.height_redo.clear()
        self.refresh_height()

    def _height_edit(self, shape: str, x: float | None = None, y: float | None = None, points=None):
        operation, preset = HEIGHT_EDIT_OPTIONS[self.height_edit_combo.currentText()]
        value = float(preset if preset is not None else self.height_amount_spin.value())
        edit = {
            "marker_type": "height",
            "target": "heightmap",
            "stage": "region_fixed_height" if operation == "set" else "local",
            "shape": shape,
            "coordinate_space": "normalized",
            "operation": operation,
            "value": value,
        }
        if points is not None:
            edit["points"] = [list(point) for point in points]
        else:
            edit.update(
                {
                    "x": float(x),
                    "y": float(y),
                    "radius_normalized": float(self.height_radius_spin.value()),
                    "width_normalized": float(self.height_radius_spin.value()) * 2.0,
                    "height_normalized": float(self.height_radius_spin.value()) * 2.0,
                }
            )
        return edit

    def finish_height_polygon(self):
        if len(self.height_polygon_points) < 3:
            self._log("高度多边形至少需要 3 个点。")
            return
        self.height_edits.append(self._height_edit("polygon", points=self.height_polygon_points))
        self.height_polygon_points.clear()
        self.height_redo.clear()
        self.refresh_height()

    def undo_height(self):
        if self.height_edits:
            self.height_redo.append(self.height_edits.pop())
            self.refresh_height()

    def redo_height(self):
        if self.height_redo:
            self.height_edits.append(self.height_redo.pop())
            self.refresh_height()

    def reset_height_controls(self):
        self.low_percentile_spin.setValue(2.0)
        self.high_percentile_spin.setValue(98.0)
        self.black_point_spin.setValue(0.0)
        self.white_point_spin.setValue(1.0)
        self.midtone_spin.setValue(1.0)
        self.invert_check.setChecked(False)
        self.height_edits.clear()
        self.height_redo.clear()
        self.refresh_height()

    def confirm_height(self):
        self.refresh_height()
        if self.height_draft is None:
            return
        self.height_master_confirmed = True
        try:
            self._write_artifacts(self.artifact_directory)
        except Exception as exc:
            self.height_master_confirmed = False
            self._show_error("保存批准主图失败", exc)
            return
        self._update_stage_state()
        self._log(
            "高度主图已确认并锁定。网格阶段不会重新读取原图进行识别或覆盖。",
            self.height_draft.report,
        )

    def unlock_height(self):
        self.height_master_confirmed = False
        self._update_stage_state()
        self._log("已主动返回高度阶段。实体蒙版仍保持锁定。")

    # --------------------------------------------------------------- artifacts
    def _write_artifacts(self, directory: Path | None):
        if directory is None or self.source_data is None or self.solid_draft is None or self.height_draft is None:
            raise ValueError("source, solid mask and height master are required")
        artifacts = export_workflow_artifacts(
            self.source_data,
            self.solid_draft.mask,
            self.height_draft.height_master,
            directory,
            solid_mask_confirmed=self.solid_mask_confirmed,
            height_master_confirmed=self.height_master_confirmed,
            solid_report=self.solid_draft.report,
            height_report=self.height_draft.report,
            source_parameters={
                "solid_mode": SOLID_MODE_OPTIONS[self.solid_mode_combo.currentText()],
                "height_mode": HEIGHT_MODE_OPTIONS[self.height_mode_combo.currentText()],
                "background_samples": list(self.background_samples),
                "solid_settings": {
                    "explicit_background": self._explicit_background(),
                    "background_tolerance": float(self.background_tolerance_spin.value()),
                },
                "normalization": {
                    "low_percentile": float(self.low_percentile_spin.value()),
                    "high_percentile": float(self.high_percentile_spin.value()),
                    "black_point": float(self.black_point_spin.value()),
                    "white_point": float(self.white_point_spin.value()),
                    "midtone": float(self.midtone_spin.value()),
                    "invert": bool(self.invert_check.isChecked()),
                },
                "height_settings": {
                    "fixed_height": float(self.fixed_height_spin.value()),
                    "line_threshold": float(self.line_threshold_spin.value()),
                    "line_depth_mm": float(self.line_depth_spin.value()),
                    "line_softness_px": float(self.line_softness_spin.value()),
                },
                "mesh_settings": {
                    "width_mm": float(self.width_spin.value()),
                    "height_mm": float(self.height_spin.value()),
                    "base_thickness_mm": float(self.base_spin.value()),
                    "relief_height_mm": float(self.relief_spin.value()),
                    "minimum_thickness_mm": float(self.minimum_thickness_spin.value()),
                    "minimum_feature_mm": float(self.min_feature_spin.value()),
                    "quality_mode": QUALITY_OPTIONS[self.quality_combo.currentText()],
                    "export_format": self.format_combo.currentText().lower(),
                    "mesh_type": "regular_shared_vertex_grid",
                },
            },
            solid_edits=self.solid_edits,
            height_edits=self.height_edits,
        )
        self.artifact_directory = Path(directory)
        return artifacts

    def save_artifacts(self):
        if self.source_data is None or self.solid_draft is None or self.height_draft is None or QFileDialog is None:
            return
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择项目与主图目录",
            str(self.artifact_directory or self.source_path.parent),
        )
        if not selected:
            return
        try:
            artifacts = self._write_artifacts(Path(selected))
            self._update_stage_state()
            self._log("主图与项目文件已保存。", artifacts.report)
        except Exception as exc:
            self._show_error("保存失败", exc)

    # --------------------------------------------------------------- mesh
    def build_and_export(self):
        if not (self.solid_mask_confirmed and self.height_master_confirmed and self.artifact_directory):
            return
        if QFileDialog is None:
            return
        suffix = self.format_combo.currentText().lower()
        default = self.artifact_directory / f"output.{suffix}"
        path, _ = QFileDialog.getSaveFileName(self, "导出闭合浮雕网格", str(default), f"{suffix.upper()} (*.{suffix})")
        if not path:
            return
        try:
            artifacts = self._write_artifacts(self.artifact_directory)
            preset = quality_preset(QUALITY_OPTIONS[self.quality_combo.currentText()])
            params = ReliefParameters(
                width_mm=float(self.width_spin.value()),
                height_mm=float(self.height_spin.value()),
                base_thickness_mm=float(self.base_spin.value()),
                relief_height_mm=float(self.relief_spin.value()),
                minimum_thickness_mm=float(self.minimum_thickness_spin.value()),
                max_grid_cells=int(preset["max_grid_cells"]),
                edge_style="straight",
            )
            result = build_relief_from_approved_heightmap(
                artifacts.paths["height_master_16bit"],
                path,
                mask_path=artifacts.paths["solid_mask"],
                parameters=params,
                quality_mode=preset["canonical_quality_mode"],
                min_feature_mm=float(self.min_feature_spin.value()),
                report_path=self.artifact_directory / "build_report.json",
            )
            self.output_status_label.setText(f"已导出：{result.output_path}")
            self._log("规则共享顶点网格已构建并导出。", result.report)
        except Exception as exc:
            self._show_error("构建失败", exc)

    # --------------------------------------------------------------- advanced
    def open_advanced(self):
        try:
            from .semantic_studio import MainWindow as AdvancedWindow

            self._advanced_window = AdvancedWindow()
            self._advanced_window.setWindowTitle("高级/实验功能（不影响默认批准主图）")
            self._advanced_window.show()
            self._log("已打开高级功能窗口。默认批准主图不会被高级窗口后台修改。")
        except Exception as exc:
            self._show_error("高级功能不可用", exc)

    def closeEvent(self, event):
        try:
            self._temporary_directory.cleanup()
        finally:
            super().closeEvent(event)


def run_standalone():
    if QApplication is None:
        raise RuntimeError("PySide6 is required for the desktop application")
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return int(app.exec())
