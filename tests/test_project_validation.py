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


def test_project_validation_rejects_insufficient_total_thickness_for_two_bases():
    project = create_project("Invalid Thickness")
    project.dimensions.base_thickness_mm = 2.0
    project.dimensions.total_thickness_mm = 3.0

    with pytest.raises(ValueError, match="at least twice base_thickness_mm"):
        _validate_project_parameters(project)


def test_project_validation_accepts_default_thickness_budget():
    project = create_project("Valid Dimensions")

    width, height = _validate_project_parameters(project)

    assert width == 80.0
    assert height == 80.0
