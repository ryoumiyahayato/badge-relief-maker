import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from badge_relief_maker.app.ui.background_jobs import DebouncedJob, JobController


def _wait(app, milliseconds=350):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()
    app.processEvents()


def test_stale_job_result_is_not_emitted_after_newer_request():
    app = QApplication.instance() or QApplication([])
    controller = JobController()
    values = []

    def worker(inputs, token, progress):
        time.sleep(float(inputs))
        token.throw_if_cancelled()
        return inputs

    controller.succeeded.connect(lambda result: values.append(result.value))
    controller.submit("height_draft", 0.10, worker)
    controller.submit("height_draft", 0.01, worker)
    _wait(app, 300)
    assert values == [0.01]


def test_debouncer_submits_only_the_last_of_twenty_changes():
    app = QApplication.instance() or QApplication([])
    values = []
    gate = DebouncedJob(lambda value: values.append(value), interval_ms=200)
    for value in range(20):
        gate.trigger(value)
    _wait(app, 300)
    assert values == [19]
