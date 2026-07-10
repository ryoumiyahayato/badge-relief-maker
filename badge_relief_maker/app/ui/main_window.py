"""Main window for the project-based desktop MVP."""

from pathlib import Path

try:
    from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception:
    QObject = object
    QThread = None
    QUrl = None
    Signal = None
    Slot = None
    QDesktopServices = None
    QCheckBox = None
    QComboBox = None
    QDoubleSpinBox = None
    QFileDialog = None
    QFormLayout = None
    QLabel = None
    QMainWindow = object
    QMessageBox = None
    QPushButton = None
    QTextEdit = None
    QVBoxLayout = None
    QWidget = object

from ..core.project_build import build_double_side_placeholder_from_project, build_side_relief_from_project
from ..core.project_io import asset_root_for, create_project, import_image_asset, load_project, save_project


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

else:
    _BuildWorker = None


class MainWindow(QMainWindow):
    """Single-side oriented GUI with persisted parameters and safe build handling."""

    def __init__(self):
        super().__init__()
        self.project = None
        self.project_path = None
        self.active_side = "front"
        self.status_label = None
        self.log_box = None
        self.last_output_path = None
        self._build_thread = None
        self._build_worker = None
        self._build_description = None
        self._build_buttons = []
        self.width_spin = None
        self.height_spin = None
        self.base_spin = None
        self.relief_spin = None
        self.minimum_thickness_spin = None
        self.rim_width_spin = None
        self.rim_height_spin = None
        self.invert_check = None
        self.mask_mode_combo = None
        self.quality_combo = None
        self.rim_profile_combo = None
        if hasattr(self, "setWindowTitle"):
            self.setWindowTitle("Badge Relief Maker")
        self._build_ui()

    def _double_spin(self, minimum, maximum, value, decimals=2):
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setDecimals(decimals)
        control.setValue(value)
        return control

    def _build_ui(self):
        if QVBoxLayout is None:
            return
        root = QWidget()
        layout = QVBoxLayout(root)

        self.status_label = QLabel("No project open")
        layout.addWidget(self.status_label)

        form = QFormLayout()
        self.width_spin = self._double_spin(0.01, 10000.0, 80.0)
        self.height_spin = self._double_spin(0.01, 10000.0, 80.0)
        self.base_spin = self._double_spin(0.0, 1000.0, 2.0)
        self.relief_spin = self._double_spin(0.0, 1000.0, 3.0)
        self.minimum_thickness_spin = self._double_spin(0.0, 1000.0, 0.8)
        self.rim_width_spin = self._double_spin(0.0, 1000.0, 0.0)
        self.rim_height_spin = self._double_spin(0.0, 1000.0, 0.0)
        self.invert_check = QCheckBox()
        self.mask_mode_combo = QComboBox()
        self.mask_mode_combo.addItems(["auto", "alpha", "luminance", "luminance-dark", "luminance-light"])
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["preview", "standard", "high"])
        self.quality_combo.setCurrentText("standard")
        self.rim_profile_combo = QComboBox()
        self.rim_profile_combo.addItems(["flat", "linear", "smooth"])

        form.addRow("Final width (mm)", self.width_spin)
        form.addRow("Final height (mm)", self.height_spin)
        form.addRow("Base thickness (mm)", self.base_spin)
        form.addRow("Relief height (mm)", self.relief_spin)
        form.addRow("Minimum thickness warning (mm)", self.minimum_thickness_spin)
        form.addRow("Mask mode", self.mask_mode_combo)
        form.addRow("Invert height", self.invert_check)
        form.addRow("Quality", self.quality_combo)
        form.addRow("Rim width (mm)", self.rim_width_spin)
        form.addRow("Rim height (mm)", self.rim_height_spin)
        form.addRow("Rim profile", self.rim_profile_combo)
        layout.addLayout(form)

        for title, handler, build_button in [
            ("New Project", self.new_project, False),
            ("Open Project", self.open_project, False),
            ("Save Project", self.save_current_project, False),
            ("Import Front Image", self.import_front_image, False),
            ("Import Back Image", self.import_back_image, False),
            ("Import Reference Image", self.import_reference_image, False),
            ("Build Front OBJ", self.build_front_obj, True),
            ("Build Front STL", self.build_front_stl, True),
            ("Build Front GLB", self.build_front_glb, True),
            ("Build Back OBJ", self.build_back_obj, True),
            ("Build Back STL", self.build_back_stl, True),
            ("Build Back GLB", self.build_back_glb, True),
            ("Build Double Placeholder OBJ", self.build_double_placeholder_obj, True),
            ("Build Double Placeholder STL", self.build_double_placeholder_stl, True),
            ("Build Double Placeholder GLB", self.build_double_placeholder_glb, True),
            ("Open Output Folder", self.open_output_folder, False),
        ]:
            button = QPushButton(title)
            button.clicked.connect(handler)
            layout.addWidget(button)
            if build_button:
                self._build_buttons.append(button)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)
        self.setCentralWidget(root)

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

    def _side_parameters(self, side_name):
        if side_name == "front":
            return self.project.front_relief
        if side_name == "back":
            return self.project.back_relief
        raise ValueError(f"unsupported GUI side: {side_name}")

    def _load_controls_from_project(self, side_name="front"):
        if self.project is None or self.width_spin is None:
            return
        self.active_side = side_name
        side = self._side_parameters(side_name)
        edge = self.project.edge
        self.width_spin.setValue(float(self.project.dimensions.width_mm))
        self.height_spin.setValue(float(self.project.dimensions.height_mm))
        self.base_spin.setValue(float(self.project.dimensions.base_thickness_mm))
        self.relief_spin.setValue(float(side.relief_height_mm))
        self.minimum_thickness_spin.setValue(float(side.minimum_thickness_mm))
        self.mask_mode_combo.setCurrentText(str(side.mask_mode))
        self.invert_check.setChecked(bool(side.invert_height))
        self.quality_combo.setCurrentText(str(side.quality_mode))
        self.rim_width_spin.setValue(float(edge.rim_width_mm))
        self.rim_height_spin.setValue(float(edge.rim_height_mm))
        self.rim_profile_combo.setCurrentText(str(edge.rim_profile))

    def _apply_controls_to_project(self, side_name=None):
        if self.project is None or self.width_spin is None:
            return
        side_name = side_name or self.active_side
        self.active_side = side_name
        side = self._side_parameters(side_name)
        edge = self.project.edge
        self.project.dimensions.width_mm = self.width_spin.value()
        self.project.dimensions.height_mm = self.height_spin.value()
        self.project.dimensions.base_thickness_mm = self.base_spin.value()
        side.relief_height_mm = self.relief_spin.value()
        side.minimum_thickness_mm = self.minimum_thickness_spin.value()
        side.mask_mode = self.mask_mode_combo.currentText()
        side.invert_height = self.invert_check.isChecked()
        side.quality_mode = self.quality_combo.currentText()
        edge.rim_width_mm = self.rim_width_spin.value()
        edge.rim_height_mm = self.rim_height_spin.value()
        edge.rim_profile = self.rim_profile_combo.currentText()
        edge.rim_enabled = edge.rim_width_mm > 0.0 and edge.rim_height_mm > 0.0
        self.project.touch()

    def new_project(self):
        try:
            self.project = create_project("Untitled Medal Project")
            self.project_path = None
            self._load_controls_from_project("front")
            self._log("New project created. Save it as a .medalproj file.")
        except Exception as exc:
            self._error("Could not create project", exc)

    def open_project(self):
        if QFileDialog is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Medal Project (*.medalproj)")
        if not path:
            return
        try:
            self.project = load_project(path)
            self.project_path = path
            self._load_controls_from_project("front")
            self._log(f"Opened project: {self.project.name}")
        except Exception as exc:
            self._error("Could not open project", exc)

    def save_current_project(self):
        try:
            if self.project is None:
                self.new_project()
            if QFileDialog is None:
                return
            path = self.project_path
            if not path:
                path, _ = QFileDialog.getSaveFileName(self, "Save project", "project.medalproj", "Medal Project (*.medalproj)")
            if not path:
                return
            self._apply_controls_to_project()
            self.project_path = save_project(self.project, path)
            self._log(f"Saved project: {self.project_path}")
        except Exception as exc:
            self._error("Could not save project", exc)

    def _ensure_saved_project(self):
        if self.project is None:
            self.new_project()
        if not self.project_path:
            self.save_current_project()
        return bool(self.project_path)

    def _import_image(self, role, is_reference=False):
        if QFileDialog is None or not self._ensure_saved_project():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        try:
            record = import_image_asset(self.project, self.project_path, path, role, is_reference=is_reference)
            self._apply_controls_to_project()
            save_project(self.project, self.project_path)
            self._log(f"Imported {role} image: {record.path}")
        except Exception as exc:
            self._error(f"Could not import {role} image", exc)

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
            gate = result.report.get("manufacturing_gate", {})
            self._log(f"Built: {result.output_path} | manufacturing gate: {gate.get('status', 'unknown')}")
        except Exception as exc:
            self._error("Could not finalize build", exc)

    def _build_failed(self, message):
        self._error(self._build_description or "Build failed", message)

    def _build_side(self, side_name, export_format):
        if not self._ensure_saved_project():
            return
        image_record = self.project.front_image if side_name == "front" else self.project.back_image
        if image_record is None:
            self._log(f"Import a {side_name} image before building relief.")
            return
        self._apply_controls_to_project(side_name)
        side_params = self._side_parameters(side_name)
        self._start_build(
            lambda: build_side_relief_from_project(
                self.project,
                self.project_path,
                side_name=side_name,
                export_format=export_format,
                quality_mode=side_params.quality_mode,
            ),
            f"Building {side_name} {export_format.upper()}",
        )

    def _build_double_placeholder(self, export_format):
        if not self._ensure_saved_project():
            return
        if self.project.front_image is None or self.project.back_image is None:
            self._log("Import both front and back images before building a double placeholder.")
            return
        self._apply_controls_to_project()
        self._start_build(
            lambda: build_double_side_placeholder_from_project(
                self.project,
                self.project_path,
                export_format=export_format,
                quality_mode=self._side_parameters(self.active_side).quality_mode,
            ),
            f"Building non-fused double placeholder {export_format.upper()}",
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

    def import_front_image(self):
        self._import_image("front", is_reference=False)

    def import_back_image(self):
        self._import_image("back", is_reference=False)

    def import_reference_image(self):
        self._import_image("reference", is_reference=True)

    def build_front_obj(self):
        self._build_side("front", "obj")

    def build_front_stl(self):
        self._build_side("front", "stl")

    def build_front_glb(self):
        self._build_side("front", "glb")

    def build_back_obj(self):
        self._build_side("back", "obj")

    def build_back_stl(self):
        self._build_side("back", "stl")

    def build_back_glb(self):
        self._build_side("back", "glb")

    def build_double_placeholder_obj(self):
        self._build_double_placeholder("obj")

    def build_double_placeholder_stl(self):
        self._build_double_placeholder("stl")

    def build_double_placeholder_glb(self):
        self._build_double_placeholder("glb")
