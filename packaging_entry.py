"""PyInstaller entry point preserving GUI launch and CLI diagnostics."""

import sys

from badge_relief_maker.app.main import main, run_gui


def packaged_main(argv=None):
    """Open the desktop editor on double-click; keep explicit CLI arguments."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        return run_gui()
    return main(arguments)


if __name__ == "__main__":
    raise SystemExit(packaged_main())
