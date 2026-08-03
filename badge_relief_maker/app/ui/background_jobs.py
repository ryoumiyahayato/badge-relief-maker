"""Cancellable, stale-result-safe background work for the editor."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable


JOB_TYPES = (
    "solid_draft",
    "height_draft",
    "full_resolution_solid_replay",
    "full_resolution_height_replay",
    "mesh_build",
)

try:  # pragma: no cover - import fallback is covered by core-only installs
    from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
except Exception:  # pragma: no cover
    QObject = object
    QRunnable = object
    QThreadPool = None
    QTimer = None
    Signal = None


class CancellationToken:
    """Thread-safe cancellation flag passed to every worker."""

    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def throw_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError("job cancelled")


class CancelledError(RuntimeError):
    pass


@dataclass
class JobRequest:
    job_type: str
    request_id: int
    inputs: Any
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
    worker: Callable | None = None

    @property
    def token(self):
        return self.cancellation_token


@dataclass
class JobResult:
    job_type: str
    request_id: int
    value: Any
    elapsed_seconds: float = 0.0


@dataclass
class JobError:
    job_type: str
    request_id: int
    error: BaseException
    cancelled: bool = False

    @property
    def message(self) -> str:
        return f"{type(self.error).__name__}: {self.error}"


if Signal is not None:

    class _JobSignals(QObject):
        progress = Signal(object, int, str)
        succeeded = Signal(object)
        failed = Signal(object)
        finished = Signal(object)


    class _JobRunnable(QRunnable):
        def __init__(self, request: JobRequest):
            super().__init__()
            self.request = request
            self.signals = _JobSignals()
            self.setAutoDelete(True)

        def run(self):  # noqa: D401 - QRunnable callback
            started = time.perf_counter()
            try:
                self.request.cancellation_token.throw_if_cancelled()
                if self.request.worker is None:
                    raise ValueError("job request has no worker")

                def progress(percent=0, message=""):
                    self.request.cancellation_token.throw_if_cancelled()
                    self.signals.progress.emit(self.request, int(percent), str(message))

                value = self.request.worker(
                    self.request.inputs,
                    self.request.cancellation_token,
                    progress,
                )
                self.request.cancellation_token.throw_if_cancelled()
                result = JobResult(
                    job_type=self.request.job_type,
                    request_id=self.request.request_id,
                    value=value,
                    elapsed_seconds=time.perf_counter() - started,
                )
                self.signals.succeeded.emit(result)
            except BaseException as exc:  # worker exceptions must reach the GUI
                self.signals.failed.emit(
                    JobError(
                        job_type=self.request.job_type,
                        request_id=self.request.request_id,
                        error=exc,
                        cancelled=isinstance(exc, CancelledError) or self.request.cancellation_token.cancelled,
                    )
                )
            finally:
                self.signals.finished.emit(self.request)


    class JobController(QObject):
        """Submit immutable snapshots to ``QThreadPool`` and reject stale results."""

        job_started = Signal(object)
        progress = Signal(object, int, str)
        succeeded = Signal(object)
        failed = Signal(object)
        finished = Signal(object)
        stale_result = Signal(object)

        def __init__(self, parent=None, *, thread_pool=None):
            super().__init__(parent)
            self.thread_pool = thread_pool or QThreadPool.globalInstance()
            self._next_ids: dict[str, int] = {}
            self._current_ids: dict[str, int] = {}
            self._requests: dict[tuple[str, int], JobRequest] = {}

        def next_request_id(self, job_type: str) -> int:
            value = self._next_ids.get(str(job_type), 0) + 1
            self._next_ids[str(job_type)] = value
            return value

        def current_request_id(self, job_type: str) -> int | None:
            return self._current_ids.get(str(job_type))

        def is_latest(self, job_type: str, request_id: int) -> bool:
            return self.current_request_id(job_type) == int(request_id)

        def invalidate(self, job_type: str) -> int:
            """Advance a job generation without submitting work.

            The editor uses this when a small synchronous preview update (for
            example, a completed stroke) supersedes a worker already in flight.
            Its late result is then stale by construction.
            """
            kind = str(job_type)
            current = self._current_ids.get(kind)
            if current is not None:
                request = self._requests.get((kind, current))
                if request is not None:
                    request.cancellation_token.cancel()
            value = self.next_request_id(kind)
            self._current_ids[kind] = value
            return value

        def submit(self, job_type, inputs=None, worker=None, *, request_id=None, cancellation_token=None):
            if isinstance(job_type, JobRequest):
                request = job_type
                if request.request_id <= 0:
                    request.request_id = self.next_request_id(request.job_type)
                if worker is not None:
                    request.worker = worker
            else:
                kind = str(job_type)
                sequence = self.next_request_id(kind) if request_id is None else int(request_id)
                self._next_ids[kind] = max(self._next_ids.get(kind, 0), sequence)
                request = JobRequest(
                    job_type=kind,
                    request_id=sequence,
                    inputs=inputs,
                    cancellation_token=cancellation_token or CancellationToken(),
                    worker=worker,
                )
            previous_id = self._current_ids.get(request.job_type)
            if previous_id is not None:
                previous = self._requests.get((request.job_type, previous_id))
                if previous is not None:
                    previous.cancellation_token.cancel()
            self._current_ids[request.job_type] = request.request_id
            self._requests[(request.job_type, request.request_id)] = request
            runnable = _JobRunnable(request)
            runnable.signals.progress.connect(self._handle_progress)
            runnable.signals.succeeded.connect(self._handle_success)
            runnable.signals.failed.connect(self._handle_failure)
            runnable.signals.finished.connect(self._handle_finished)
            self.job_started.emit(request)
            self.thread_pool.start(runnable)
            return request

        def cancel(self, job_type: str | None = None, request_id: int | None = None) -> bool:
            cancelled = False
            for (kind, sequence), request in list(self._requests.items()):
                if job_type is not None and kind != str(job_type):
                    continue
                if request_id is not None and sequence != int(request_id):
                    continue
                request.cancellation_token.cancel()
                cancelled = True
            return cancelled

        @Slot(object, int, str)
        def _handle_progress(self, request, percent, message):
            if self.is_latest(request.job_type, request.request_id):
                self.progress.emit(request, int(percent), str(message))

        @Slot(object)
        def _handle_success(self, result):
            if self.is_latest(result.job_type, result.request_id):
                self.succeeded.emit(result)
            else:
                self.stale_result.emit(result)

        @Slot(object)
        def _handle_failure(self, error):
            if self.is_latest(error.job_type, error.request_id):
                self.failed.emit(error)

        @Slot(object)
        def _handle_finished(self, request):
            self._requests.pop((request.job_type, request.request_id), None)
            self.finished.emit(request)


    class DebouncedJob(QObject):
        """A single-shot 200 ms gate for slider and combo-box changes."""

        triggered = Signal(object)

        def __init__(self, callback, parent=None, interval_ms: int = 200):
            super().__init__(parent)
            self.callback = callback
            self.timer = QTimer(self)
            self.timer.setSingleShot(True)
            self.timer.setInterval(int(interval_ms))
            self.timer.timeout.connect(self._fire)
            self._payload = None

        def trigger(self, payload=None):
            self._payload = payload
            self.timer.start()

        def cancel(self):
            self.timer.stop()

        def _fire(self):
            payload = self._payload
            self._payload = None
            self.triggered.emit(payload)
            self.callback(payload)

else:  # pragma: no cover

    class JobController:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for background GUI jobs")

    class DebouncedJob:
        def __init__(self, callback, *args, **kwargs):
            self.callback = callback

        def trigger(self, payload=None):
            self.callback(payload)

        def cancel(self):
            return None


__all__ = [
    "CancellationToken",
    "CancelledError",
    "DebouncedJob",
    "JOB_TYPES",
    "JobController",
    "JobError",
    "JobRequest",
    "JobResult",
]
