"""Main window placeholder for the future GUI."""

try:
    from PySide6.QtWidgets import QMainWindow
except Exception:
    QMainWindow = object


class MainWindow(QMainWindow):
    """Empty main window shell."""

    def __init__(self):
        super().__init__()
        if hasattr(self, "setWindowTitle"):
            self.setWindowTitle("Badge Relief Maker")
