import pytest

from badge_relief_maker.app.core.project_build import _validate_project_parameters
from badge_relief_maker.app.core.project_io import create_project


def test_project_validation_rejects_negative_dimensions():
    project = create_project("Invalid Dimensions")
    project.dimensions.width_mm = -1.0

    with pytest.raises(ValueError, match="width_mm must be positive"):
        _validate_project_parameters(project)


def test_project_validation_rejects_non_numeric_dimensions():
    project = create_project("Invalid Dimensions")
    project.dimensions.height_mm = "wide"

    with pytest.raises(ValueError, match="height_mm must be numeric"):
        _validate_project_parameters(project)


def test_single_side_validation_accepts_one_base_thickness_budget():
    project = create_project("Single Side Thickness")
    project.dimensions.base_thickness_mm = 2.0
    project.dimensions.total_thickness_mm = 2.0

    width, height = _validate_project_parameters(project, double_side=False, side_name="front")

    assert width == 80.0
    assert height == 80.0


def test_single_side_validation_rejects_total_thinner_than_base():
    project = create_project("Invalid Single Thickness")
    project.dimensions.base_thickness_mm = 2.0
    project.dimensions.total_thickness_mm = 1.5

    with pytest.raises(ValueError, match="at least base_thickness_mm"):
        _validate_project_parameters(project, double_side=False, side_name="front")


def test_single_side_validation_ignores_unused_malformed_other_side():
    project = create_project("Independent Sides")
    project.back_relief.relief_height_mm = "broken"

    width, height = _validate_project_parameters(project, double_side=False, side_name="front")

    assert width == 80.0
    assert height == 80.0


def test_selected_back_side_still_validates_back_settings():
    project = create_project("Invalid Back")
    project.back_relief.relief_height_mm = "broken"

    with pytest.raises(ValueError, match="back relief_height_mm must be numeric"):
        _validate_project_parameters(project, double_side=False, side_name="back")


def test_double_side_validation_rejects_insufficient_total_thickness_for_two_bases():
    project = create_project("Invalid Double Thickness")
    project.dimensions.base_thickness_mm = 2.0
    project.dimensions.total_thickness_mm = 3.0

    with pytest.raises(ValueError, match="at least twice base_thickness_mm"):
        _validate_project_parameters(project, double_side=True)


def test_double_side_validation_checks_both_side_settings():
    project = create_project("Invalid Double Side")
    project.back_relief.mask_mode = "unsupported"

    with pytest.raises(ValueError, match="unsupported back mask_mode"):
        _validate_project_parameters(project, double_side=True)


def test_project_validation_accepts_default_double_side_thickness_budget():
    project = create_project("Valid Dimensions")

    width, height = _validate_project_parameters(project, double_side=True)

    assert width == 80.0
    assert height == 80.0
