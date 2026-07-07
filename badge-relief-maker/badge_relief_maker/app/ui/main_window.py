"""Main window placeholder for the future PySide6 GUI."""

from __future__ import annotations

try:
    from PySide6.QtWidgets import QMainWindow
except Exception:  # pragma: no cover - lets tests run without GUI deps
    QMainWindow = object


class MainWindow(QMainWindow):
    """Empty main window shell.

    Future panels should include image import, mask preview, parameter controls,
    mesh preview, repair checks and export actions.
    """

    def __init__(self) -> None:
        super().__init__()
        if hasattr(self, "setWindowTitle"):
            self.setWindowTitle("Badge Relief Maker")
