"""Application package."""

__all__ = ["main"]


def main(argv=None):
    """Load the CLI entry point only when it is invoked."""
    from .main import main as run

    return run(argv)
