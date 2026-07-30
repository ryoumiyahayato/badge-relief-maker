"""Crash-safe atomic file replacement for project and export artifacts."""

import os
import tempfile
from contextlib import contextmanager, suppress
from pathlib import Path


@contextmanager
def atomic_writer(path, mode, encoding=None):
    """Write beside a target, flush it to disk, then atomically replace it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary_path = Path(temporary_name)
    try:
        kwargs = {} if "b" in mode else {"encoding": encoding or "utf-8", "newline": "\n"}
        with os.fdopen(file_descriptor, mode, **kwargs) as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        with suppress(OSError):
            os.close(file_descriptor)
        with suppress(OSError):
            temporary_path.unlink()
        raise
