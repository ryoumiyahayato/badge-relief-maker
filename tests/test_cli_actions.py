import pytest

from badge_relief_maker.app.main import main


def test_cli_rejects_conflicting_import_actions():
    with pytest.raises(SystemExit) as exc_info:
        main(["--project-path", "test.medalproj", "--import-front", "front.png", "--import-back", "back.png"])

    assert exc_info.value.code == 2


def test_cli_rejects_conflicting_primary_action_categories():
    with pytest.raises(SystemExit) as exc_info:
        main(["--new-project", "Test", "--project-path", "test.medalproj", "--input", "input.png", "--output", "output.obj"])

    assert exc_info.value.code == 2


def test_cli_requires_both_direct_input_and_output():
    with pytest.raises(SystemExit) as exc_info:
        main(["--input", "input.png"])

    assert exc_info.value.code == 2


def test_cli_without_action_is_importable_and_returns_zero(capsys):
    assert main([]) == 0
    assert "Badge Relief Maker" in capsys.readouterr().out
