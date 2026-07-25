"""Default UI routing for the focused semantic editor."""

try:  # Keep core-only imports usable when Qt is unavailable.
    from . import grayscale_studio as _base
    from .semantic_studio import MainWindow as _SemanticMainWindow

    _base.MainWindow = _SemanticMainWindow
except Exception:
    pass
