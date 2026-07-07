from badge_relief_maker.app.main import main
from badge_relief_maker.app.core.mesh_exporter import supported_formats


def test_entrypoint_runs():
    assert main() == 0


def test_supported_formats():
    assert {"stl", "obj", "glb"}.issubset(supported_formats())
