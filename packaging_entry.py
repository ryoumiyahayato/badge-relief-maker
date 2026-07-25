"""PyInstaller entry point for the local grayscale heightmap application."""

import sys

from badge_relief_maker.app.main import main


def run_desktop_app():
    """Launch the Chinese-first grayscale studio."""
    from PySide6.QtWidgets import QApplication

    from badge_relief_maker.app.ui.semantic_studio import MainWindow

    app = QApplication(sys.argv[:1])
    window = MainWindow()
    window.show()
    return int(app.exec())


def run_gui():
    """Compatibility alias retained for packaging tests and existing callers."""
    return run_desktop_app()


def packaged_main(argv=None):
    """Open the desktop application on double-click; retain explicit CLI diagnostics."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        return run_gui()
    return main(arguments)


if __name__ == "__main__":
    raise SystemExit(packaged_main())
