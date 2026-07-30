"""Reusable project-window shell for the desktop relief editor."""

import json
from pathlib import Path

try:
    from PySide6.QtCore import QObject, QThread, Qt, QUrl, Signal, Slot
    from PySide6.QtGui import QCloseEvent, QDesktopServices, QPixmap
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSplitter,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception:
    QObject = object
    QThread = None
    Qt = None
    QUrl = None
    Signal = None
    Slot = None
    QCloseEvent = object
    QDesktopServices = None
    QPixmap = None
    QCheckBox = None
    QComboBox = None
    QDoubleSpinBox = None
    QFileDialog = None
    QFormLayout = None
    QGridLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QMainWindow = object
    QMessageBox = None
    QPushButton = None
    QScrollArea = None
    QSplitter = None
    QTabWidget = None
    QTextEdit = None
    QVBoxLayout = None
    QWidget = object

from ..core.project_build import (
    build_double_side_placeholder_from_project,
    build_fused_double_side_from_project,
    build_side_relief_from_project,
)
from ..core.options import EDGE_STYLES, FOOTPRINT_MODES, HEIGHT_MODES, MASK_MODES, PROCESS_PROFILES, QUALITY_MODES, RIM_PROFILES, SIDE_NAMES
from ..core.project_io import asset_root_for, create_project, import_image_asset, load_project, save_project
from ..core.project_model import DimensionParameters, DoubleSideParameters, EdgeParameters, ReliefSideParameters


if Signal is not None:

    class _BuildWorker(QObject):
        finished = Signal(object)
        failed = Signal(str)

        def __init__(self, operation):
            super().__init__()
            self.operation = operation

        @Slot()
        def run(self):
            try:
                self.finished.emit(self.operation())
            except Exception as exc:
                self.failed.emit(str(exc))


    class _PreviewLabel(QLabel):
        clicked = Signal(float, float)

        def __init__(self, title):
            super().__init__(title)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setMinimumSize(230, 230)
            self.setStyleSheet("QLabel { background: #20242a; color: #cfd5dd; border: 1px solid #4b5563; }")
            self.setScaledContents(True)

        def mousePressEvent(self, event):
            if self.width() > 0 and self.height() > 0:
                self.clicked.emit(
                    float(np_clip(event.position().x() / self.width())),
                    float(np_clip(event.position().y() / self.height())),
                )
            super().mousePressEvent(event)

else:
    _BuildWorker = None
    _PreviewLabel = None


def np_clip(value):
    return min(max(float(value), 0.0), 1.0)


class ProjectWindow(QMainWindow):
    """Project lifecycle, controls and build orchestration shared by editor UIs."""

    def __init__(self):
        super().__init__()
        self.project = None
        self.project_path = None
        self.active_side = "front"
        self.last_output_path = None
        self._dirty = False
        self._loading_controls = False
        self._crop_first_point = None
        self._perspective_points = []
        self._build_thread = None
        self._build_worker = None
        self._build_description = None
        self._build_buttons = []
        self._controls = []
        self.setWindowTitle("Badge Relief Maker")
        self.resize(1400, 900)
        self._build_ui()

    def _double_spin(self, minimum, maximum, value, decimals=3):
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setDecimals(decimals)
        control.setValue(value)
        self._controls.append(control)
        return control

    def _combo(self, values, current=None):
        control = QComboBox()
        control.addItems(values)
        if current is not None:
            control.setCurrentText(current)
        self._controls.append(control)
        return control

    def _group(self, title, rows):
        group = QGroupBox(title)
        form = QFormLayout(group)
        for label, control in rows:
            form.addRow(label, control)
        return group

    def _build_ui(self):
        if QVBoxLayout is None:
            return
        dimensions = DimensionParameters()
        relief = ReliefSideParameters()
        edge = EdgeParameters()
        double_side = DoubleSideParameters()
        root = QWidget()
        root_layout = QVBoxLayout(root)
        header = QHBoxLayout()
        self.status_label = QLabel("No project open")
        self.side_combo = self._combo(SIDE_NAMES.values, SIDE_NAMES.default)
        header.addWidget(self.status_label, 1)
        header.addWidget(QLabel("Editing side"))
        header.addWidget(self.side_combo)
        root_layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_root = QWidget()
        controls_layout = QVBoxLayout(controls_root)
        self.controls_layout = controls_layout

        self.width_spin = self._double_spin(0.01, 10000.0, dimensions.width_mm)
        self.height_spin = self._double_spin(0.01, 10000.0, dimensions.height_mm)
        self.total_spin = self._double_spin(0.01, 1000.0, dimensions.total_thickness_mm)
        self.base_spin = self._double_spin(0.0, 1000.0, dimensions.base_thickness_mm)
        controls_layout.addWidget(
            self._group(
                "Dimensions",
                [
                    ("Final width (mm)", self.width_spin),
                    ("Final height (mm)", self.height_spin),
                    ("Double body thickness (mm)", self.total_spin),
                    ("Single base thickness (mm)", self.base_spin),
                ],
            )
        )

        self.relief_spin = self._double_spin(0.0, 1000.0, relief.relief_height_mm)
        self.minimum_thickness_spin = self._double_spin(0.0, 1000.0, relief.minimum_thickness_mm)
        self.uniform_height_spin = self._double_spin(0.0, 1.0, relief.uniform_height_normalized)
        self.smooth_spin = self._double_spin(0.0, 1.0, relief.smooth_strength)
        self.sharp_spin = self._double_spin(0.0, 1.0, relief.detail_sharpness)
        self.invert_check = QCheckBox()
        self._controls.append(self.invert_check)
        self.mask_mode_combo = self._combo(MASK_MODES.values, MASK_MODES.default)
        self.height_mode_combo = self._combo(HEIGHT_MODES.values, HEIGHT_MODES.default)
        self.quality_combo = self._combo(QUALITY_MODES.values, QUALITY_MODES.default)
        self.process_combo = self._combo(PROCESS_PROFILES.values, PROCESS_PROFILES.default)
        controls_layout.addWidget(
            self._group(
                "Face processing",
                [
                    ("Relief height (mm)", self.relief_spin),
                    ("Minimum wall warning (mm)", self.minimum_thickness_spin),
                    ("Mask mode", self.mask_mode_combo),
                    ("Height mode", self.height_mode_combo),
                    ("Uniform height", self.uniform_height_spin),
                    ("Global smoothing", self.smooth_spin),
                    ("Detail sharpness", self.sharp_spin),
                    ("Invert height", self.invert_check),
                    ("Quality", self.quality_combo),
                    ("Process profile", self.process_combo),
                ],
            )
        )

        self.rim_width_spin = self._double_spin(0.0, 1000.0, edge.rim_width_mm)
        self.rim_height_spin = self._double_spin(0.0, 1000.0, edge.rim_height_mm)
        self.rim_profile_combo = self._combo(RIM_PROFILES.values, RIM_PROFILES.default)
        self.edge_style_combo = self._combo(EDGE_STYLES.values, EDGE_STYLES.default)
        self.bevel_spin = self._double_spin(0.0, 1000.0, edge.bevel_mm)
        self.radius_spin = self._double_spin(0.0, 1000.0, edge.radius_mm)
        controls_layout.addWidget(
            self._group(
                "Edge geometry",
                [
                    ("Rim width (mm)", self.rim_width_spin),
                    ("Rim height (mm)", self.rim_height_spin),
                    ("Rim profile", self.rim_profile_combo),
                    ("Edge style", self.edge_style_combo),
                    ("Bevel/inset (mm)", self.bevel_spin),
                    ("Rounded radius (mm)", self.radius_spin),
                ],
            )
        )

        self.back_scale_spin = self._double_spin(0.05, 20.0, double_side.back_scale)
        self.back_rotation_spin = self._double_spin(-180.0, 180.0, double_side.back_rotation_deg)
        self.back_offset_x_spin = self._double_spin(-10000.0, 10000.0, double_side.back_offset_x_mm)
        self.back_offset_y_spin = self._double_spin(-10000.0, 10000.0, double_side.back_offset_y_mm)
        self.flip_back_check = QCheckBox()
        self.flip_back_check.setChecked(double_side.flip_back_horizontal)
        self._controls.append(self.flip_back_check)
        self.footprint_combo = self._combo(FOOTPRINT_MODES.values, FOOTPRINT_MODES.default)
        controls_layout.addWidget(
            self._group(
                "Fused double alignment",
                [
                    ("Back scale", self.back_scale_spin),
                    ("Back rotation (deg)", self.back_rotation_spin),
                    ("Back X offset (mm)", self.back_offset_x_spin),
                    ("Back Y offset (mm)", self.back_offset_y_spin),
                    ("Flip viewed-back image", self.flip_back_check),
                    ("Footprint", self.footprint_combo),
                ],
            )
        )

        self.edit_tool_combo = self._combo(
            [
                "inspect",
                "mask add",
                "mask remove",
                "height set",
                "height add",
                "height subtract",
                "height smooth",
                "layer set",
                "layer locked",
                "crop rectangle",
                "perspective quadrilateral",
            ],
            "inspect",
        )
        self.brush_radius_spin = self._double_spin(0.001, 0.5, 0.03)
        self.brush_height_spin = self._double_spin(0.0, 1.0, 0.7)
        refresh_button = QPushButton("Refresh previews")
        refresh_button.clicked.connect(self.refresh_previews)
        clear_button = QPushButton("Clear crop and visual edits")
        clear_button.clicked.connect(self.clear_visual_edits)
        controls_layout.addWidget(
            self._group(
                "Preview editing",
                [
                    ("Click tool", self.edit_tool_combo),
                    ("Brush radius (normalized)", self.brush_radius_spin),
                    ("Height / smooth strength", self.brush_height_spin),
                    ("", refresh_button),
                    ("", clear_button),
                ],
            )
        )

        controls_layout.addStretch(1)
        controls_scroll.setWidget(controls_root)
        splitter.addWidget(controls_scroll)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.right_layout = right_layout
        preview_layout = QHBoxLayout()
        self.source_preview = _PreviewLabel("Source image")
        self.mask_preview = _PreviewLabel("Exact final mask overlay")
        self.height_preview = _PreviewLabel("Final heightmap")
        for preview in (self.source_preview, self.mask_preview, self.height_preview):
            preview_layout.addWidget(preview)
        self.source_preview.clicked.connect(self._preview_clicked)
        self.mask_preview.clicked.connect(self._preview_clicked)
        self.height_preview.clicked.connect(self._preview_clicked)
        right_layout.addLayout(preview_layout)

        action_grid = QGridLayout()
        actions = [
            ("New", self.new_project, False),
            ("Open", self.open_project, False),
            ("Save", self.save_current_project, False),
            ("Import Front", self.import_front_image, False),
            ("Import Back", self.import_back_image, False),
            ("Import Reference", self.import_reference_image, False),
            ("Front OBJ", self.build_front_obj, True),
            ("Front STL", self.build_front_stl, True),
            ("Front GLB", self.build_front_glb, True),
            ("Back OBJ", self.build_back_obj, True),
            ("Back STL", self.build_back_stl, True),
            ("Back GLB", self.build_back_glb, True),
            ("Fused Double OBJ", self.build_double_obj, True),
            ("Fused Double STL", self.build_double_stl, True),
            ("Fused Double GLB", self.build_double_glb, True),
            ("Inspection Placeholder OBJ", self.build_double_placeholder_obj, True),
            ("Open Output Folder", self.open_output_folder, False),
        ]
        for index, (title, handler, build_button) in enumerate(actions):
            button = QPushButton(title)
            button.clicked.connect(handler)
            action_grid.addWidget(button, index // 3, index % 3)
            if build_button:
                self._build_buttons.append(button)
        right_layout.addLayout(action_grid)

        tabs = QTabWidget()
        self.report_box = QTextEdit()
        self.report_box.setReadOnly(True)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        tabs.addTab(self.report_box, "Build report")
        tabs.addTab(self.log_box, "Log")
        right_layout.addWidget(tabs, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

        self.side_combo.currentTextChanged.connect(self._side_changed)
        for control in self._controls:
            if isinstance(control, QDoubleSpinBox):
                control.valueChanged.connect(self._mark_dirty)
            elif isinstance(control, QComboBox) and control is not self.side_combo:
                control.currentTextChanged.connect(self._mark_dirty)
            elif isinstance(control, QCheckBox):
                control.toggled.connect(self._mark_dirty)

    def _log(self, message):
        if self.log_box is not None:
            self.log_box.append(str(message))
        if self.status_label is not None:
            self.status_label.setText(str(message))

    def _error(self, context, error):
        message = f"{context}: {error}"
        self._log(message)
        if QMessageBox is not None:
            QMessageBox.critical(self, "Badge Relief Maker", message)

    def _mark_dirty(self, *_):
        if not self._loading_controls and self.project is not None:
            self._dirty = True

    def _side_parameters(self, side_name):
        if side_name == "front":
            return self.project.front_relief
        if side_name == "back":
            return self.project.back_relief
        raise ValueError(f"unsupported GUI side: {side_name}")

    def _load_controls_from_project(self, side_name="front"):
        if self.project is None:
            return
        self._loading_controls = True
        try:
            self.active_side = side_name
            self.side_combo.setCurrentText(side_name)
            side = self._side_parameters(side_name)
            edge = self.project.edge
            double = self.project.double_side
            self.width_spin.setValue(float(self.project.dimensions.width_mm))
            self.height_spin.setValue(float(self.project.dimensions.height_mm))
            self.total_spin.setValue(float(self.project.dimensions.total_thickness_mm))
            self.base_spin.setValue(float(self.project.dimensions.base_thickness_mm))
            self.relief_spin.setValue(float(side.relief_height_mm))
            self.minimum_thickness_spin.setValue(float(side.minimum_thickness_mm))
            self.uniform_height_spin.setValue(float(side.uniform_height_normalized))
            self.smooth_spin.setValue(float(side.smooth_strength))
            self.sharp_spin.setValue(float(side.detail_sharpness))
            self.mask_mode_combo.setCurrentText(str(side.mask_mode))
            self.height_mode_combo.setCurrentText(str(side.height_mode))
            self.invert_check.setChecked(bool(side.invert_height))
            self.quality_combo.setCurrentText(str(side.quality_mode))
            self.process_combo.setCurrentText(str(side.process_profile))
            self.rim_width_spin.setValue(float(edge.rim_width_mm))
            self.rim_height_spin.setValue(float(edge.rim_height_mm))
            self.rim_profile_combo.setCurrentText(str(edge.rim_profile))
            self.edge_style_combo.setCurrentText(str(edge.edge_style))
            self.bevel_spin.setValue(float(edge.bevel_mm))
            self.radius_spin.setValue(float(edge.radius_mm))
            self.back_scale_spin.setValue(float(double.back_scale))
            self.back_rotation_spin.setValue(float(double.back_rotation_deg))
            self.back_offset_x_spin.setValue(float(double.back_offset_x_mm))
            self.back_offset_y_spin.setValue(float(double.back_offset_y_mm))
            self.flip_back_check.setChecked(bool(double.flip_back_horizontal))
            self.footprint_combo.setCurrentText(str(double.footprint_mode))
        finally:
            self._loading_controls = False

    def _apply_controls_to_project(self, side_name=None):
        if self.project is None:
            return
        side_name = side_name or self.active_side
        side = self._side_parameters(side_name)
        edge = self.project.edge
        double = self.project.double_side
        self.project.dimensions.width_mm = self.width_spin.value()
        self.project.dimensions.height_mm = self.height_spin.value()
        self.project.dimensions.total_thickness_mm = self.total_spin.value()
        self.project.dimensions.base_thickness_mm = self.base_spin.value()
        side.relief_height_mm = self.relief_spin.value()
        side.minimum_thickness_mm = self.minimum_thickness_spin.value()
        side.uniform_height_normalized = self.uniform_height_spin.value()
        side.smooth_strength = self.smooth_spin.value()
        side.detail_sharpness = self.sharp_spin.value()
        side.mask_mode = self.mask_mode_combo.currentText()
        side.height_mode = self.height_mode_combo.currentText()
        side.invert_height = self.invert_check.isChecked()
        side.quality_mode = self.quality_combo.currentText()
        side.process_profile = self.process_combo.currentText()
        edge.rim_width_mm = self.rim_width_spin.value()
        edge.rim_height_mm = self.rim_height_spin.value()
        edge.rim_profile = self.rim_profile_combo.currentText()
        edge.rim_enabled = edge.rim_width_mm > 0.0 and edge.rim_height_mm > 0.0
        edge.edge_style = self.edge_style_combo.currentText()
        edge.bevel_mm = self.bevel_spin.value()
        edge.radius_mm = self.radius_spin.value()
        double.enabled = True
        double.back_scale = self.back_scale_spin.value()
        double.back_rotation_deg = self.back_rotation_spin.value()
        double.back_offset_x_mm = self.back_offset_x_spin.value()
        double.back_offset_y_mm = self.back_offset_y_spin.value()
        double.flip_back_horizontal = self.flip_back_check.isChecked()
        double.footprint_mode = self.footprint_combo.currentText()
        self.project.touch()

    def _confirm_discard_changes(self):
        if not self._dirty or self.project is None or QMessageBox is None:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            "Save changes before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return bool(self.save_current_project())
        return True

    def new_project(self):
        if not self._confirm_discard_changes():
            return False
        self.project = create_project("Untitled Medal Project")
        self.project_path = None
        self._dirty = False
        self._load_controls_from_project("front")
        self._clear_previews()
        self._log("New project created. Save it as a .medalproj file.")
        return True

    def open_project(self):
        if QFileDialog is None or not self._confirm_discard_changes():
            return False
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Medal Project (*.medalproj)")
        if not path:
            return False
        try:
            self.project = load_project(path)
            self.project_path = path
            self._dirty = False
            self._load_controls_from_project("front")
            self.refresh_previews()
            self._log(f"Opened project: {self.project.name}")
            return True
        except Exception as exc:
            self._error("Could not open project", exc)
            return False

    def save_current_project(self):
        try:
            if self.project is None:
                self.project = create_project("Untitled Medal Project")
            if QFileDialog is None:
                return False
            path = self.project_path
            if not path:
                path, _ = QFileDialog.getSaveFileName(self, "Save project", "project.medalproj", "Medal Project (*.medalproj)")
            if not path:
                return False
            self._apply_controls_to_project()
            self.project_path = save_project(self.project, path)
            self._dirty = False
            self._log(f"Saved project: {self.project_path}")
            return True
        except Exception as exc:
            self._error("Could not save project", exc)
            return False

    def _ensure_saved_project(self):
        if self.project is None:
            self.new_project()
        if not self.project_path:
            self.save_current_project()
        return bool(self.project_path)

    def _import_image(self, role, is_reference=False):
        if QFileDialog is None or not self._ensure_saved_project():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if not path:
            return
        try:
            record = import_image_asset(self.project, self.project_path, path, role, is_reference=is_reference)
            self._apply_controls_to_project()
            save_project(self.project, self.project_path)
            self._dirty = False
            if role in {"front", "back"}:
                self._load_controls_from_project(role)
                self.refresh_previews()
            self._log(f"Imported {role} image: {record.path}")
        except Exception as exc:
            self._error(f"Could not import {role} image", exc)

    def _side_changed(self, side_name):
        if self.project is None or self._loading_controls or side_name == self.active_side:
            return
        self._apply_controls_to_project(self.active_side)
        self._load_controls_from_project(side_name)
        self.refresh_previews()

    def _image_record(self, side_name=None):
        if self.project is None:
            return None
        side_name = side_name or self.active_side
        return self.project.front_image if side_name == "front" else self.project.back_image

    def _set_preview(self, label, path, empty_text):
        if QPixmap is None or not path or not Path(path).is_file():
            label.setText(empty_text)
            return
        label.setPixmap(QPixmap(str(path)))

    def _clear_previews(self):
        self.source_preview.clear()
        self.source_preview.setText("Source image")
        self.mask_preview.clear()
        self.mask_preview.setText("Exact final mask overlay")
        self.height_preview.clear()
        self.height_preview.setText("Final heightmap")

    def refresh_previews(self):
        raise NotImplementedError("a project-window editor must implement preview rendering")

    def _preview_clicked(self, x_normalized, y_normalized):
        raise NotImplementedError("a project-window editor must implement preview interactions")

    def clear_visual_edits(self):
        raise NotImplementedError("a project-window editor must implement visual edit reset")

    def _set_building(self, building):
        for button in self._build_buttons:
            button.setEnabled(not building)

    def _start_build(self, operation, description):
        if QThread is None or _BuildWorker is None:
            self._error(description, "PySide6 worker support is unavailable")
            return
        if self._build_thread is not None:
            self._log("A build is already running.")
            return
        self._build_description = description
        self._set_building(True)
        self._log(f"{description}...")
        self._build_thread = QThread(self)
        self._build_worker = _BuildWorker(operation)
        self._build_worker.moveToThread(self._build_thread)
        self._build_thread.started.connect(self._build_worker.run)
        self._build_worker.finished.connect(self._build_finished)
        self._build_worker.failed.connect(self._build_failed)
        self._build_worker.finished.connect(self._build_thread.quit)
        self._build_worker.failed.connect(self._build_thread.quit)
        self._build_worker.finished.connect(self._build_worker.deleteLater)
        self._build_worker.failed.connect(self._build_worker.deleteLater)
        self._build_thread.finished.connect(self._build_thread.deleteLater)
        self._build_thread.finished.connect(self._clear_build_worker)
        self._build_thread.start()

    def _clear_build_worker(self):
        self._build_thread = None
        self._build_worker = None
        self._build_description = None
        self._set_building(False)

    def _build_finished(self, result):
        try:
            self.last_output_path = result.output_path
            save_project(self.project, self.project_path)
            self._dirty = False
            gate = result.report.get("manufacturing_gate", {})
            self.report_box.setPlainText(json.dumps(result.report, indent=2, ensure_ascii=False, default=str))
            self._log(f"Built: {result.output_path} | manufacturing gate: {gate.get('status', 'unknown')}")
        except Exception as exc:
            self._error("Could not finalize build", exc)

    def _build_failed(self, message):
        self._error(self._build_description or "Build failed", message)

    def _build_side(self, side_name, export_format):
        if not self._ensure_saved_project():
            return
        if self._image_record(side_name) is None:
            self._log(f"Import a {side_name} image before building relief.")
            return
        if side_name != self.active_side:
            self._apply_controls_to_project(self.active_side)
        else:
            self._apply_controls_to_project(side_name)
        quality = self._side_parameters(side_name).quality_mode
        self._start_build(
            lambda: build_side_relief_from_project(self.project, self.project_path, side_name, export_format, quality),
            f"Building {side_name} {export_format.upper()}",
        )

    def _build_double(self, export_format, fused=True):
        if not self._ensure_saved_project():
            return
        if self.project.front_image is None or self.project.back_image is None:
            self._log("Import both front and back images first.")
            return
        self._apply_controls_to_project(self.active_side)
        operation = build_fused_double_side_from_project if fused else build_double_side_placeholder_from_project
        label = "fused double-side" if fused else "non-fused inspection placeholder"
        self._start_build(
            lambda: operation(self.project, self.project_path, export_format=export_format, quality_mode=self.quality_combo.currentText()),
            f"Building {label} {export_format.upper()}",
        )

    def open_output_folder(self):
        path = Path(self.last_output_path).parent if self.last_output_path else None
        if path is None and self.project_path:
            path = asset_root_for(self.project_path) / "exports"
        if path is None or not path.exists():
            self._log("No output folder is available yet.")
            return
        if QDesktopServices is not None and QUrl is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def closeEvent(self, event: QCloseEvent):
        if self._build_thread is not None:
            if QMessageBox is not None:
                QMessageBox.warning(self, "Build running", "Wait for the active build before closing the application.")
            event.ignore()
            return
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()

    def import_front_image(self): self._import_image("front", False)
    def import_back_image(self): self._import_image("back", False)
    def import_reference_image(self): self._import_image("reference", True)
    def build_front_obj(self): self._build_side("front", "obj")
    def build_front_stl(self): self._build_side("front", "stl")
    def build_front_glb(self): self._build_side("front", "glb")
    def build_back_obj(self): self._build_side("back", "obj")
    def build_back_stl(self): self._build_side("back", "stl")
    def build_back_glb(self): self._build_side("back", "glb")
    def build_double_obj(self): self._build_double("obj", True)
    def build_double_stl(self): self._build_double("stl", True)
    def build_double_glb(self): self._build_double("glb", True)
    def build_double_placeholder_obj(self): self._build_double("obj", False)
    def build_double_placeholder_stl(self): self._build_double("stl", False)
    def build_double_placeholder_glb(self): self._build_double("glb", False)
