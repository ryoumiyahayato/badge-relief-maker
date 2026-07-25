"""Simplified Chinese desktop application for phase-one grayscale heightmap work.

This window deliberately exposes one workflow only:

    source image -> review/correct regions -> export editable grayscale master

The existing project/core modules remain the persistence and processing backend.
Mesh generation is not presented as a phase-one action.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

try:
    from PySide6.QtCore import QObject, QSettings, QThread, Qt, QUrl, Signal, Slot
    from PySide6.QtGui import QDesktopServices, QPixmap
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
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSplitter,
        QStatusBar,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover - allows core-only installations to import the module
    QObject = object
    QSettings = None
    QThread = None
    Qt = None
    QUrl = None
    Signal = None
    Slot = None
    QDesktopServices = None
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
    QProgressBar = None
    QPushButton = None
    QScrollArea = None
    QSplitter = None
    QStatusBar = None
    QTextEdit = None
    QVBoxLayout = None
    QWidget = object

from ..core.project_build import export_side_heightmap_master_from_project, relief_parameters_from_project
from ..core.project_io import asset_root_for, create_project, import_image_asset, load_project, resolve_project_asset, save_project
from ..core.single_side_pipeline import prepare_relief_field


APP_TITLE = "勋章灰度图生成器"
APP_SUBTITLE = "第一阶段：单张图片 → 可编辑高精度灰度高度图"
QUALITY_OPTIONS = {
    "标准（4096 像素）": 4096,
    "高精（8192 像素）": 8192,
    "极致（12288 像素）": 12288,
}
REGION_OPERATIONS = {
    "查看区域": None,
    "挖空／设为背景": "background",
    "设为承载面": "surface",
    "抬高为前景构件": "raise",
    "压低为凹陷／阴影": "recess",
}


if Signal is not None:

    class _TaskWorker(QObject):
        finished = Signal(object)
        failed = Signal(str)

        def __init__(self, operation):
            super().__init__()
            self.operation = operation

        @Slot()
        def run(self):
            try:
                self.finished.emit(self.operation())
            except Exception as exc:  # pragma: no cover - surfaced to GUI
                self.failed.emit(str(exc))


    class _ImagePanel(QLabel):
        clicked = Signal(float, float)

        def __init__(self, title, clickable=False):
            super().__init__()
            self._title = str(title)
            self._clickable = bool(clickable)
            self._pixmap_source = None
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setMinimumSize(260, 300)
            self.setText(self._title)
            self.setFrameShape(QFrame.Shape.StyledPanel)
            self.setStyleSheet(
                "QLabel { background:#171a1f; color:#9aa4b2; border:1px solid #313844; "
                "border-radius:8px; padding:8px; }"
            )

        def clear_image(self, text=None):
            self._pixmap_source = None
            self.clear()
            self.setText(text or self._title)

        def set_image(self, path):
            pixmap = QPixmap(str(path)) if path else QPixmap()
            if pixmap.isNull():
                self.clear_image(f"{self._title}\n无法读取预览")
                return
            self._pixmap_source = pixmap
            self._update_scaled_pixmap()

        def _target_rect(self):
            if self._pixmap_source is None or self._pixmap_source.isNull():
                return None
            source_size = self._pixmap_source.size()
            scaled_size = source_size.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            left = (self.width() - scaled_size.width()) / 2.0
            top = (self.height() - scaled_size.height()) / 2.0
            return left, top, float(scaled_size.width()), float(scaled_size.height())

        def _update_scaled_pixmap(self):
            if self._pixmap_source is None or self._pixmap_source.isNull():
                return
            scaled = self._pixmap_source.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)

        def resizeEvent(self, event):
            self._update_scaled_pixmap()
            super().resizeEvent(event)

        def mousePressEvent(self, event):
            if self._clickable:
                rect = self._target_rect()
                if rect is not None:
                    left, top, width, height = rect
                    x = float(event.position().x())
                    y = float(event.position().y())
                    if left <= x <= left + width and top <= y <= top + height:
                        self.clicked.emit((x - left) / max(width, 1.0), (y - top) / max(height, 1.0))
            super().mousePressEvent(event)

else:
    _TaskWorker = None
    _ImagePanel = None


class MainWindow(QMainWindow):
    """Chinese-first, reduced-control grayscale heightmap desktop application."""

    def __init__(self):
        super().__init__()
        self.project = None
        self.project_path = None
        self.output_directory = None
        self._preview_transform = None
        self._task_thread = None
        self._task_worker = None
        self._task_callback = None
        self._settings = QSettings("BadgeReliefMaker", "GrayscaleStudio") if QSettings is not None else None

        self.setWindowTitle(APP_TITLE)
        self.resize(1480, 900)
        self.setMinimumSize(1100, 720)
        self._build_ui()
        self._install_menu()
        self._restore_settings()
        self._set_project_ready(False)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        if QWidget is None:
            return
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 14, 16, 12)
        root_layout.setSpacing(12)

        heading = QHBoxLayout()
        heading_text = QVBoxLayout()
        title = QLabel(APP_TITLE)
        title.setStyleSheet("font-size:24px; font-weight:700; color:#f4f7fb;")
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setStyleSheet("font-size:13px; color:#9aa4b2;")
        heading_text.addWidget(title)
        heading_text.addWidget(subtitle)
        heading.addLayout(heading_text, 1)
        self.project_label = QLabel("尚未导入图片")
        self.project_label.setStyleSheet("color:#cbd5e1; padding:8px 12px; background:#202630; border-radius:8px;")
        heading.addWidget(self.project_label)
        root_layout.addLayout(heading)

        workflow = QHBoxLayout()
        self.import_button = QPushButton("1  导入图片")
        self.generate_button = QPushButton("2  生成／刷新灰度图")
        self.export_button = QPushButton("3  导出高精度灰度图")
        self.open_folder_button = QPushButton("打开导出目录")
        self.phase_two_button = QPushButton("第二阶段：由批准灰度图生成 3D")
        self.phase_two_button.setEnabled(False)
        self.phase_two_button.setToolTip("第二阶段将在灰度图通过复核后启用；当前软件先完成灰度图生成。")
        for button in (self.import_button, self.generate_button, self.export_button):
            button.setMinimumHeight(40)
            button.setStyleSheet(
                "QPushButton { background:#2f6fed; color:white; border:0; border-radius:7px; padding:8px 14px; font-weight:600; }"
                "QPushButton:hover { background:#3b7cff; } QPushButton:disabled { background:#39414d; color:#7b8491; }"
            )
        for button in (self.open_folder_button, self.phase_two_button):
            button.setMinimumHeight(40)
        workflow.addWidget(self.import_button)
        workflow.addWidget(self.generate_button)
        workflow.addWidget(self.export_button)
        workflow.addWidget(self.open_folder_button)
        workflow.addStretch(1)
        workflow.addWidget(self.phase_two_button)
        root_layout.addLayout(workflow)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumWidth(285)
        controls_scroll.setMaximumWidth(380)
        controls_root = QWidget()
        controls_layout = QVBoxLayout(controls_root)
        controls_layout.setContentsMargins(2, 2, 8, 2)
        controls_layout.setSpacing(10)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(QUALITY_OPTIONS.keys())
        self.quality_combo.setCurrentText("高精（8192 像素）")
        self.smooth_spin = self._spin(0.0, 1.0, 0.03, 0.01)
        self.detail_spin = self._spin(0.0, 1.0, 0.45, 0.01)
        self.base_level_spin = self._spin(0.0, 1.0, 0.28, 0.01)
        self.invert_check = QCheckBox("反转高低（通常不要开启）")
        generation_group = QGroupBox("灰度生成")
        generation_form = QFormLayout(generation_group)
        generation_form.addRow("输出精度", self.quality_combo)
        generation_form.addRow("边缘净化", self.smooth_spin)
        generation_form.addRow("细节保留", self.detail_spin)
        generation_form.addRow("基础层级", self.base_level_spin)
        generation_form.addRow("", self.invert_check)
        controls_layout.addWidget(generation_group)

        self.region_operation_combo = QComboBox()
        self.region_operation_combo.addItems(REGION_OPERATIONS.keys())
        self.region_amount_spin = self._spin(0.0, 1.0, 0.18, 0.01)
        self.undo_button = QPushButton("撤销最后一次区域修改")
        self.reset_button = QPushButton("清除全部人工修正")
        region_group = QGroupBox("区域修正")
        region_form = QFormLayout(region_group)
        region_form.addRow("点击区域后执行", self.region_operation_combo)
        region_form.addRow("抬高／压低强度", self.region_amount_spin)
        region_form.addRow("", self.undo_button)
        region_form.addRow("", self.reset_button)
        controls_layout.addWidget(region_group)

        guidance = QTextEdit()
        guidance.setReadOnly(True)
        guidance.setMaximumHeight(210)
        guidance.setPlainText(
            "操作顺序\n"
            "1. 导入实物照片、扫描图或线稿。\n"
            "2. 点击“生成／刷新灰度图”。\n"
            "3. 在中间的区域图上选择挖空、承载面、抬高或压低。\n"
            "4. 每次修正都会累积保存；只有点击撤销或清除时才会删除。\n"
            "5. 导出16位PNG、32位TIFF、线稿层、实体蒙版和空隙蒙版。\n"
            "6. 灰度图确认后再进入第二阶段生成3D。"
        )
        controls_layout.addWidget(guidance)
        self.correction_label = QLabel("人工修正：0 项")
        self.correction_label.setStyleSheet("color:#cbd5e1;")
        controls_layout.addWidget(self.correction_label)
        controls_layout.addStretch(1)
        controls_scroll.setWidget(controls_root)
        splitter.addWidget(controls_scroll)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(10, 0, 0, 0)
        preview_grid = QGridLayout()
        preview_grid.setSpacing(10)
        self.source_preview = _ImagePanel("原始图片")
        self.region_preview = _ImagePanel("区域／边界图（可点击修改）", clickable=True)
        self.height_preview = _ImagePanel("实际灰度高度图预览")
        preview_grid.addWidget(self._panel_with_title("原始图片", self.source_preview), 0, 0)
        preview_grid.addWidget(self._panel_with_title("区域与边界", self.region_preview), 0, 1)
        preview_grid.addWidget(self._panel_with_title("灰度高度图", self.height_preview), 0, 2)
        workspace_layout.addLayout(preview_grid, 1)

        self.summary_box = QTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMaximumHeight(150)
        self.summary_box.setPlaceholderText("这里显示识别结果、灰度图规格和导出位置。")
        workspace_layout.addWidget(self.summary_box)
        splitter.addWidget(workspace)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(4)
        root_layout.addWidget(self.progress)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("请先导入一张图片。")

        self.setStyleSheet(
            "QMainWindow, QWidget { background:#111418; color:#e6ebf2; font-size:13px; }"
            "QGroupBox { border:1px solid #303743; border-radius:8px; margin-top:10px; padding-top:8px; font-weight:600; }"
            "QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 4px; }"
            "QComboBox, QDoubleSpinBox, QTextEdit { background:#1b2027; border:1px solid #343c48; border-radius:6px; padding:6px; }"
            "QPushButton { background:#252b34; border:1px solid #394250; border-radius:6px; padding:7px 12px; }"
            "QPushButton:hover { background:#303844; }"
            "QScrollArea { border:0; }"
        )

        self.import_button.clicked.connect(self.import_image)
        self.generate_button.clicked.connect(self.generate_previews)
        self.export_button.clicked.connect(self.export_heightmap)
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.undo_button.clicked.connect(self.undo_last_correction)
        self.reset_button.clicked.connect(self.clear_all_corrections)
        self.region_preview.clicked.connect(self.apply_region_operation)
        for control in (self.smooth_spin, self.detail_spin, self.base_level_spin):
            control.valueChanged.connect(self._mark_settings_changed)
        self.invert_check.toggled.connect(self._mark_settings_changed)

    def _install_menu(self):
        if self.menuBar() is None:
            return
        file_menu = self.menuBar().addMenu("文件")
        import_action = file_menu.addAction("导入图片…")
        import_action.triggered.connect(self.import_image)
        open_action = file_menu.addAction("打开已有项目…")
        open_action.triggered.connect(self.open_project)
        file_menu.addSeparator()
        export_action = file_menu.addAction("导出高精度灰度图…")
        export_action.triggered.connect(self.export_heightmap)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("退出")
        exit_action.triggered.connect(self.close)

        help_menu = self.menuBar().addMenu("帮助")
        about_action = help_menu.addAction("当前阶段说明")
        about_action.triggered.connect(self.show_phase_information)

    @staticmethod
    def _spin(minimum, maximum, value, step):
        control = QDoubleSpinBox()
        control.setRange(float(minimum), float(maximum))
        control.setDecimals(3)
        control.setSingleStep(float(step))
        control.setValue(float(value))
        return control

    @staticmethod
    def _panel_with_title(title, panel):
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setStyleSheet("font-weight:600; color:#d8dee8; padding:2px 4px;")
        layout.addWidget(label)
        layout.addWidget(panel, 1)
        return frame

    # ------------------------------------------------------------ persistence
    def _restore_settings(self):
        if self._settings is None:
            return
        output = self._settings.value("output_directory", "")
        if output:
            self.output_directory = str(output)

    def _save_settings(self):
        if self._settings is not None and self.output_directory:
            self._settings.setValue("output_directory", self.output_directory)

    def _workspace_for_image(self, image_path):
        image_path = Path(image_path)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = image_path.parent / f"{image_path.stem}_灰度图项目_{stamp}"
        root.mkdir(parents=True, exist_ok=False)
        return root

    def _apply_controls_to_project(self):
        if self.project is None:
            return
        side = self.project.front_relief
        side.height_mode = "emboss"
        side.mask_mode = "auto"
        side.quality_mode = "high"
        side.smooth_strength = float(self.smooth_spin.value())
        side.detail_sharpness = float(self.detail_spin.value())
        side.uniform_height_normalized = float(self.base_level_spin.value())
        side.invert_height = bool(self.invert_check.isChecked())
        self.project.touch()

    def _save_project(self):
        if self.project is None or not self.project_path:
            return
        self._apply_controls_to_project()
        save_project(self.project, self.project_path)

    def _set_project_ready(self, ready):
        for control in (
            self.generate_button,
            self.export_button,
            self.region_operation_combo,
            self.region_amount_spin,
            self.undo_button,
            self.reset_button,
        ):
            control.setEnabled(bool(ready))
        self.open_folder_button.setEnabled(bool(self.output_directory and Path(self.output_directory).exists()))

    def _mark_settings_changed(self, *_):
        if self.project is not None:
            self.statusBar().showMessage("参数已修改，请点击“生成／刷新灰度图”。")

    # --------------------------------------------------------------- projects
    def import_image(self):
        if QFileDialog is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入徽章、勋章或奖章图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)",
        )
        if not path:
            return
        try:
            workspace = self._workspace_for_image(path)
            self.project_path = str(workspace / f"{Path(path).stem}.medalproj")
            self.project = create_project(Path(path).stem)
            save_project(self.project, self.project_path)
            import_image_asset(self.project, self.project_path, path, "front")
            save_project(self.project, self.project_path)
            self.output_directory = str(workspace / "灰度图导出")
            Path(self.output_directory).mkdir(parents=True, exist_ok=True)
            self._save_settings()
            self.project_label.setText(f"当前项目：{Path(path).name}")
            self._load_controls_from_project()
            self._set_project_ready(True)
            self.generate_previews()
        except Exception as exc:
            self._show_error("导入图片失败", exc)

    def open_project(self):
        if QFileDialog is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开灰度图项目", "", "灰度图项目 (*.medalproj)")
        if not path:
            return
        try:
            project = load_project(path)
            if project.front_image is None:
                raise ValueError("该项目没有正面图片。")
            self.project = project
            self.project_path = path
            self.output_directory = str(Path(path).parent / "灰度图导出")
            Path(self.output_directory).mkdir(parents=True, exist_ok=True)
            self.project_label.setText(f"当前项目：{project.name}")
            self._load_controls_from_project()
            self._set_project_ready(True)
            self.generate_previews()
        except Exception as exc:
            self._show_error("打开项目失败", exc)

    def _load_controls_from_project(self):
        side = self.project.front_relief
        self.smooth_spin.setValue(float(side.smooth_strength))
        self.detail_spin.setValue(float(side.detail_sharpness))
        self.base_level_spin.setValue(float(side.uniform_height_normalized))
        self.invert_check.setChecked(bool(side.invert_height))
        self._update_correction_count()

    # ------------------------------------------------------------ task runner
    def _run_task(self, description, operation, callback):
        if self._task_thread is not None:
            return
        self._set_busy(True, description)
        thread = QThread(self)
        worker = _TaskWorker(operation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._task_finished)
        worker.failed.connect(self._task_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._task_thread = thread
        self._task_worker = worker
        self._task_callback = callback
        thread.finished.connect(self._task_cleared)
        thread.start()

    def _task_finished(self, result):
        callback = self._task_callback
        try:
            if callback is not None:
                callback(result)
        except Exception as exc:
            self._show_error("处理结果失败", exc)
        finally:
            self._set_busy(False, "处理完成")

    def _task_failed(self, message):
        self._set_busy(False, "处理失败")
        self._show_error("处理失败", message)

    def _task_cleared(self):
        self._task_thread = None
        self._task_worker = None
        self._task_callback = None

    def _set_busy(self, busy, message):
        for button in (self.import_button, self.generate_button, self.export_button, self.undo_button, self.reset_button):
            button.setEnabled(not busy and (button is self.import_button or self.project is not None))
        self.progress.setRange(0, 0 if busy else 1)
        if not busy:
            self.progress.setValue(0)
        self.statusBar().showMessage(str(message))

    # -------------------------------------------------------------- previews
    def _source_record(self):
        return self.project.front_image if self.project is not None else None

    def generate_previews(self):
        record = self._source_record()
        if record is None or not self.project_path:
            return
        self._save_project()
        project = self.project
        project_path = self.project_path

        def operation():
            params, _ = relief_parameters_from_project(project, "front", "high")
            source_path = resolve_project_asset(project_path, record.path)
            preview_dir = asset_root_for(project_path) / "previews" / "grayscale_studio"
            preview_dir.mkdir(parents=True, exist_ok=True)
            prepared = prepare_relief_field(source_path, params, preview_dir=preview_dir)
            return prepared, str(source_path)

        self._run_task("正在分析图片并生成灰度图预览…", operation, self._preview_ready)

    def _preview_ready(self, payload):
        prepared, source_path = payload
        self._preview_transform = prepared.image_transform
        paths = prepared.report.get("preview_paths", {})
        self.source_preview.set_image(paths.get("source_preview") or source_path)
        self.region_preview.set_image(paths.get("lineart_region_preview") or paths.get("mask_overlay_preview"))
        self.height_preview.set_image(paths.get("heightmap_preview"))
        report = prepared.report
        grid = report.get("geometry_grid") or report.get("grid_shape") or list(prepared.heightmap.shape)
        region_report = report.get("lineart_region_graph", {})
        self.summary_box.setPlainText(
            "灰度图预览已生成。\n"
            f"处理网格：{grid}\n"
            f"图片类型判断：{report.get('artwork_interpretation', '自动')}\n"
            f"待确认区域：{region_report.get('unresolved_region_count', 0)}\n"
            "屏幕中的灰度图是8位预览；正式导出为16位PNG和32位浮点TIFF。"
        )
        self._update_correction_count()
        self.statusBar().showMessage("预览已刷新。可在区域图上继续修正，或直接导出灰度图。")

    # ----------------------------------------------------------- corrections
    def apply_region_operation(self, x_normalized, y_normalized):
        if self.project is None:
            return
        role = REGION_OPERATIONS.get(self.region_operation_combo.currentText())
        if role is None:
            self.statusBar().showMessage(f"区域位置：x={x_normalized:.4f}, y={y_normalized:.4f}")
            return
        side = self.project.front_relief
        side.lineart_region_overrides.append(
            {
                "x": float(x_normalized),
                "y": float(y_normalized),
                "coordinate_space": "final_normalized",
                "role": role,
                "amount": float(self.region_amount_spin.value()),
            }
        )
        self._save_project()
        self._update_correction_count()
        self.generate_previews()

    def undo_last_correction(self):
        if self.project is None:
            return
        side = self.project.front_relief
        if side.lineart_region_overrides:
            side.lineart_region_overrides.pop()
        elif self.project.manual_markers:
            self.project.manual_markers.pop()
        elif side.mask_edits:
            side.mask_edits.pop()
        else:
            self.statusBar().showMessage("没有可撤销的人工修正。")
            return
        self._save_project()
        self._update_correction_count()
        self.generate_previews()

    def clear_all_corrections(self):
        if self.project is None or QMessageBox is None:
            return
        answer = QMessageBox.warning(
            self,
            "清除全部人工修正",
            "这会删除当前项目中已经累积的挖空、抬高、压低和局部修正。确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        side = self.project.front_relief
        side.lineart_region_overrides = []
        side.mask_edits = []
        side.region_layers = []
        self.project.manual_markers = []
        self._save_project()
        self._update_correction_count()
        self.generate_previews()

    def _update_correction_count(self):
        if self.project is None:
            self.correction_label.setText("人工修正：0 项")
            return
        side = self.project.front_relief
        count = len(side.lineart_region_overrides) + len(side.mask_edits) + len(side.region_layers) + len(self.project.manual_markers)
        self.correction_label.setText(f"人工修正：{count} 项（按顺序累积保存）")

    # --------------------------------------------------------------- export
    def export_heightmap(self):
        if self.project is None or not self.project_path or QFileDialog is None:
            return
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择灰度图导出目录",
            str(self.output_directory or Path(self.project_path).parent),
        )
        if not selected:
            return
        self.output_directory = str(Path(selected).resolve())
        Path(self.output_directory).mkdir(parents=True, exist_ok=True)
        self._save_settings()
        self._save_project()
        long_edge = QUALITY_OPTIONS[self.quality_combo.currentText()]
        project = self.project
        project_path = self.project_path
        output_directory = self.output_directory

        def operation():
            return export_side_heightmap_master_from_project(
                project,
                project_path,
                "front",
                long_edge_px=long_edge,
                output_dir=output_directory,
                quality_mode="high",
            )

        self._run_task("正在导出16位PNG和32位TIFF灰度主图…", operation, self._export_ready)

    def _export_ready(self, result):
        report = result.report
        self.open_folder_button.setEnabled(True)
        self.summary_box.setPlainText(
            "灰度主图导出完成。\n"
            f"分辨率：{report.get('width_px')} × {report.get('height_px')} 像素\n"
            f"16位PNG：{report.get('output_path')}\n"
            f"32位TIFF、线稿层、实体蒙版和空隙蒙版位于：{report.get('output_directory')}\n"
            "当前交付物是灰度图；3D生成仍属于第二阶段。"
        )
        preview_name = report.get("files", {}).get("preview")
        if preview_name:
            self.height_preview.set_image(Path(report.get("output_directory")) / preview_name)
        self.statusBar().showMessage("灰度图已导出。请先检查16位PNG或32位TIFF，再进入第二阶段。")
        if QMessageBox is not None:
            QMessageBox.information(self, APP_TITLE, "灰度图导出完成。\n\n已生成16位PNG、32位TIFF及配套蒙版。")

    def open_output_folder(self):
        if not self.output_directory:
            return
        path = Path(self.output_directory)
        path.mkdir(parents=True, exist_ok=True)
        if QDesktopServices is not None and QUrl is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # --------------------------------------------------------------- misc
    def show_phase_information(self):
        if QMessageBox is None:
            return
        QMessageBox.information(
            self,
            "当前阶段说明",
            "当前软件只验收第一阶段：从单张图片生成可编辑的高精度灰度高度图。\n\n"
            "正式导出包含16位PNG、32位浮点TIFF、线稿层、实体蒙版和空隙蒙版。\n"
            "灰度图未通过复核前，软件不会把3D预览当作完成结果。",
        )

    def _show_error(self, title, error):
        message = str(error)
        self.statusBar().showMessage(f"{title}：{message}")
        if QMessageBox is not None:
            QMessageBox.critical(self, title, message)

    def closeEvent(self, event):
        try:
            self._save_project()
            self._save_settings()
        finally:
            super().closeEvent(event)


def run_standalone():
    """Launch the grayscale studio directly for manual development."""
    if QApplication is None:
        raise RuntimeError("PySide6 is required for the desktop application")
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
