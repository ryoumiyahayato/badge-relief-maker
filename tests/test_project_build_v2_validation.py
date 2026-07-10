import pytest

from badge_relief_maker.app.core.project_build import _resolve_double_quality, _validate_project_parameters
from badge_relief_maker.app.core.project_io import create_project


def test_fused_body_thickness_is_independent_from_single_side_base():
    project = create_project("Fused Thickness")
    project.dimensions.base_thickness_mm = 2.0
    project.dimensions.total_thickness_mm = 1.0

    width, height = _validate_project_parameters(project, fused=True)

    assert width == 80.0
    assert height == 80.0


def test_placeholder_still_requires_room_for_two_complete_bases():
    project = create_project("Placeholder Thickness")
    project.dimensions.base_thickness_mm = 2.0
    project.dimensions.total_thickness_mm = 3.0

    with pytest.raises(ValueError, match="at least twice base_thickness_mm"):
        _validate_project_parameters(project, double_side=True)


def test_v2_normalized_processing_parameters_are_bounded():
    project = create_project("Invalid Smoothing")
    project.front_relief.smooth_strength = 1.5

    with pytest.raises(ValueError, match="smooth_strength must be at most 1.0"):
        _validate_project_parameters(project, side_name="front")


def test_fused_alignment_requires_supported_footprint_mode():
    project = create_project("Invalid Alignment")
    project.double_side.footprint_mode = "automatic-magic"

    with pytest.raises(ValueError, match="footprint_mode"):
        _validate_project_parameters(project, fused=True)


def test_fused_build_requires_one_process_profile_for_the_whole_object():
    project = create_project("Mixed Process")
    project.front_relief.process_profile = "resin"
    project.back_relief.process_profile = "cnc"

    with pytest.raises(ValueError, match="process_profile must match"):
        _validate_project_parameters(project, fused=True)


def test_double_build_rejects_ambiguous_saved_quality_modes():
    project = create_project("Mixed Quality")
    project.front_relief.quality_mode = "preview"
    project.back_relief.quality_mode = "high"

    with pytest.raises(ValueError, match="quality_mode must match"):
        _resolve_double_quality(project)


def test_double_build_explicit_quality_override_applies_to_both_sides():
    project = create_project("Override Quality")
    project.front_relief.quality_mode = "preview"
    project.back_relief.quality_mode = "high"

    assert _resolve_double_quality(project, "standard") == "standard"


def test_double_build_normalizes_equivalent_saved_quality_aliases():
    project = create_project("Quality Aliases")
    project.front_relief.quality_mode = "low"
    project.back_relief.quality_mode = "draft"

    assert _resolve_double_quality(project) == "preview"
