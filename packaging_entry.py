"""PyInstaller entry point preserving the normal CLI and optional GUI."""

from badge_relief_maker.app.main import cli


if __name__ == "__main__":
    raise SystemExit(cli())
