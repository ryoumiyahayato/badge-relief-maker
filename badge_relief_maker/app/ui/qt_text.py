"""Small Qt text helpers used by the Windows-friendly desktop UI."""

from __future__ import annotations

try:
    from PySide6.QtGui import QFont, QFontDatabase
except Exception:  # pragma: no cover - core-only installations
    QFont = QFontDatabase = None


WINDOWS_FONT_FALLBACKS = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI")


def install_readable_ui_font(application) -> str | None:
    """Select an installed system font without bundling or shipping fonts."""
    if application is None or QFont is None or QFontDatabase is None:
        return None
    installed = {str(family) for family in QFontDatabase.families()}
    selected = next((family for family in WINDOWS_FONT_FALLBACKS if family in installed), None)
    if selected is None:
        return str(application.font().family())
    font = QFont(application.font())
    font.setFamily(selected)
    application.setFont(font)
    return selected


__all__ = ["WINDOWS_FONT_FALLBACKS", "install_readable_ui_font"]
