import subprocess
import sys

import numpy as np

from badge_relief_maker.app.core.components import component_labels
from badge_relief_maker.app.core.mesh_analysis import PROCESS_PROFILE_LIMITS
from badge_relief_maker.app.core.mesh_exporter import supported_formats
from badge_relief_maker.app.core.options import EXPORT_FORMATS, PROCESS_PROFILES, QUALITY_MODES
from badge_relief_maker.app.core.project_model import MedalProject
from badge_relief_maker.app.core.quality_modes import QUALITY_PRESETS


def test_quality_and_process_tables_match_their_shared_catalogs():
    assert tuple(QUALITY_PRESETS) == QUALITY_MODES.values
    assert tuple(PROCESS_PROFILE_LIMITS) == PROCESS_PROFILES.values


def test_project_defaults_are_owned_by_shared_catalogs():
    project = MedalProject(name="Architecture contract")
    assert project.front_relief.quality_mode == QUALITY_MODES.default
    assert project.front_relief.process_profile == PROCESS_PROFILES.default
    assert project.back_relief.quality_mode == QUALITY_MODES.default
    assert project.back_relief.process_profile == PROCESS_PROFILES.default


def test_export_dispatch_matches_the_shared_format_catalog():
    assert supported_formats() == set(EXPORT_FORMATS.values)


def test_component_labels_are_deterministic_and_keep_diagonals_separate():
    mask = np.asarray([[True, False], [False, True]], dtype=bool)
    labels, components = component_labels(mask)

    assert labels.tolist() == [[0, -1], [-1, 1]]
    assert [component.pixels for component in components] == [((0, 0),), ((1, 1),)]


def test_main_module_is_a_real_cli_entrypoint():
    completed = subprocess.run(
        [sys.executable, "-m", "badge_relief_maker.app.main", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "usage:" in completed.stdout
    assert "RuntimeWarning" not in completed.stderr
