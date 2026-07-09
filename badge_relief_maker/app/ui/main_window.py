"""Main window skeleton for the desktop MVP."""

try:
    from PySide6.QtWidgets import (
        QFileDialog,
        QLabel,
        QMainWindow,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception:
    QFileDialog = None
    QLabel = None
    QMainWindow = object
    QPushButton = None
    QTextEdit = None
    QVBoxLayout = None
    QWidget = object

from ..core.project_build import build_side_relief_from_project
from ..core.project_io import create_project, import_image_asset, load_project, save_project


class MainWindow(QMainWindow):
    """Minimal project-based GUI shell.

    This is intentionally simple. It provides the top-level workflow hooks for
    project creation, save/open, image import and side relief generation. The
    heavy editor panels will be added later.
    """

    def __init__(self):
        super().__init__()
        self.project = None
        self.project_path = None
        self.status_label = None
        self.log_box = None
        if hasattr(self, "setWindowTitle"):
            self.setWindowTitle("Badge Relief Maker")
        self._build_ui()

    def _build_ui(self):
        if QVBoxLayout is None:
            return
        root = QWidget()
        layout = QVBoxLayout(root)

        self.status_label = QLabel("No project open")
        layout.addWidget(self.status_label)

        for title, handler in [
            ("New Project", self.new_project),
            ("Open Project", self.open_project),
            ("Save Project", self.save_current_project),
            ("Import Front Image", self.import_front_image),
            ("Import Back Image", self.import_back_image),
            ("Import Reference Image", self.import_reference_image),
            ("Build Front OBJ", self.build_front_obj),
            ("Build Front STL", self.build_front_stl),
            ("Build Back OBJ", self.build_back_obj),
            ("Build Back STL", self.build_back_stl),
        ]:
            button = QPushButton(title)
            button.clicked.connect(handler)
            layout.addWidget(button)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)
        self.setCentralWidget(root)

    def _log(self, message):
        if self.log_box is not None:
            self.log_box.append(str(message))
        if self.status_label is not None:
            self.status_label.setText(str(message))

    def new_project(self):
        self.project = create_project("Untitled Medal Project")
        self.project_path = None
        self._log("New project created. Save it as a .medalproj file.")

    def open_project(self):
        if QFileDialog is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Medal Project (*.medalproj)")
        if not path:
            return
        self.project = load_project(path)
        self.project_path = path
        self._log(f"Opened project: {self.project.name}")

    def save_current_project(self):
        if self.project is None:
            self.new_project()
        if QFileDialog is None:
            return
        path = self.project_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save project", "project.medalproj", "Medal Project (*.medalproj)")
        if not path:
            return
        self.project_path = save_project(self.project, path)
        self._log(f"Saved project: {self.project_path}")

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
        record = import_image_asset(self.project, self.project_path, path, role, is_reference=is_reference)
        save_project(self.project, self.project_path)
        self._log(f"Imported {role} image: {record.path}")

    def _build_side(self, side_name, export_format):
        if not self._ensure_saved_project():
            return
        image_record = self.project.front_image if side_name == "front" else self.project.back_image
        if image_record is None:
            self._log(f"Import a {side_name} image before building relief.")
            return
        side_params = self.project.front_relief if side_name == "front" else self.project.back_relief
        result = build_side_relief_from_project(
            self.project,
            self.project_path,
            side_name=side_name,
            export_format=export_format,
            quality_mode=side_params.quality_mode,
        )
        save_project(self.project, self.project_path)
        self._log(f"Built {side_name} relief: {result.output_path}")

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

    def build_back_obj(self):
        self._build_side("back", "obj")

    def build_back_stl(self):
        self._build_side("back", "stl")
