import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image

from badge_relief_maker.app.main import main


def _write_approved(tmp_path):
    height = np.linspace(0.0, 1.0, 40 * 50, dtype=np.float32).reshape(40, 50)
    mask = np.ones((40, 50), dtype=bool)
    mask[:3] = False
    height[~mask] = 0.0
    height_path = tmp_path / "height_master_16bit.png"
    mask_path = tmp_path / "solid_mask.png"
    Image.fromarray(np.round(height * 65535).astype(np.uint16)).save(height_path)
    Image.fromarray(mask.astype(np.uint8) * 255).save(mask_path)
    return height_path, mask_path


def test_approved_cli_bypasses_source_and_writes_report(tmp_path):
    height_path, mask_path = _write_approved(tmp_path)
    output = tmp_path / "result.stl"
    report = tmp_path / "result_report.json"

    status = main(
        [
            "--approved-heightmap",
            str(height_path),
            "--approved-solid-mask",
            str(mask_path),
            "--output",
            str(output),
            "--width-mm",
            "100",
            "--height-mm",
            "80",
            "--base-mm",
            "2",
            "--relief-mm",
            "3",
            "--quality",
            "draft",
            "--min-feature-mm",
            "0.3",
            "--build-report",
            str(report),
        ]
    )

    assert status == 0
    assert output.is_file()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["source_image_used_for_mesh"] is False
    assert payload["semantic_inference"] is False
    assert payload["automatic_line_interpretation"] is False
    assert payload["regular_shared_vertex_grid"] is True
    assert payload["quality_mode"] == "draft"
    assert len(payload["input_hashes"]["approved_height_master_sha256"]) == 64


def test_approved_cli_requires_both_master_artifacts(tmp_path, capsys):
    height_path, _ = _write_approved(tmp_path)
    status = main(["--approved-heightmap", str(height_path), "--output", str(tmp_path / "bad.stl")])
    captured = capsys.readouterr()
    assert status == 2
    assert "require both" in captured.err


def test_simple_modules_import_when_scipy_is_unavailable(tmp_path):
    script = r'''
import builtins
real_import = builtins.__import__
def blocked(name, *args, **kwargs):
    if name == "scipy" or name.startswith("scipy."):
        raise ModuleNotFoundError("blocked scipy")
    return real_import(name, *args, **kwargs)
builtins.__import__ = blocked
from badge_relief_maker.app import main
from badge_relief_maker.app.core.approved_heightmap_builder import build_relief_from_approved_heightmap
from badge_relief_maker.app.core.deterministic_workflow import draft_solid_mask, draft_height_master
from badge_relief_maker.app.ui import deterministic_studio
print("simple-path-ok")
'''
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "simple-path-ok" in completed.stdout


def test_gui_smoke_argument_uses_timed_default_studio(monkeypatch):
    import importlib

    app_main = importlib.import_module("badge_relief_maker.app.main")

    called = {}

    def fake_run_gui(*, smoke_seconds=None):
        called["smoke_seconds"] = smoke_seconds
        return 0

    monkeypatch.setattr(app_main, "run_gui", fake_run_gui)
    assert app_main.main(["--gui-smoke-seconds", "3"]) == 0
    assert called == {"smoke_seconds": 3.0}
