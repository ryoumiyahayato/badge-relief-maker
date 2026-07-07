"""Parameter objects for relief building."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReliefParameters:
    """User controlled dimensions for a single side relief build."""

    width_mm: float = 80.0
    height_mm: float = 80.0
    base_thickness_mm: float = 2.0
    relief_height_mm: float = 3.0
    invert_height: bool = False
    alpha_threshold: int = 1
    minimum_thickness_mm: float = 0.8


@dataclass(frozen=True)
class ReliefBuildResult:
    """Return value for a build step."""

    vertices: object
    faces: object
    report: dict
    output_path: str | None = None
