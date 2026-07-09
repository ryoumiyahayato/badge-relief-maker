"""Project data model for medal relief projects."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


PROJECT_FILE_VERSION = 1


def utc_now_iso():
    """Return a stable UTC timestamp string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ImageRecord:
    """One image stored inside a project."""

    role: str
    path: str
    original_path: str = ""
    is_reference: bool = False
    quality_label: str = "unknown"
    notes: str = ""
    preprocessing: dict = field(default_factory=dict)


@dataclass
class OutlineData:
    """Current project outline state."""

    outline_type: str = "unknown"
    points: list = field(default_factory=list)
    confidence: float = 0.0
    manually_edited: bool = False


@dataclass
class DimensionParameters:
    """Real world dimensions in millimeters."""

    width_mm: float = 80.0
    height_mm: float = 80.0
    total_thickness_mm: float = 4.0
    base_thickness_mm: float = 2.0


@dataclass
class EdgeParameters:
    """Parametric side and rim settings."""

    edge_style: str = "straight"
    bevel_mm: float = 0.0
    radius_mm: float = 0.0
    rim_enabled: bool = False
    rim_width_mm: float = 0.0
    rim_width_px: int = 0
    rim_height_mm: float = 0.0
    rim_profile: str = "flat"
    use_smoothed_side_walls: bool = False
    contour_smoothing_iterations: int = 1


@dataclass
class ReliefSideParameters:
    """Relief parameters for one face."""

    enabled: bool = True
    relief_height_mm: float = 3.0
    background_depth_mm: float = 0.0
    layer_count: int = 4
    height_mode: str = "grayscale"
    quality_mode: str = "standard"


@dataclass
class ManualMarker:
    """Record of a manual correction or hint."""

    marker_type: str
    target: str
    data: dict = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class ExportRecord:
    """Record of one export action."""

    path: str
    export_format: str
    created_at: str = field(default_factory=utc_now_iso)
    notes: str = ""
    report: dict = field(default_factory=dict)


@dataclass
class MedalProject:
    """Persistent project data for one badge or medal relief project."""

    name: str
    file_version: int = PROJECT_FILE_VERSION
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    same_physical_object: bool = True
    front_image: ImageRecord | None = None
    back_image: ImageRecord | None = None
    reference_images: list = field(default_factory=list)
    outline: OutlineData = field(default_factory=OutlineData)
    dimensions: DimensionParameters = field(default_factory=DimensionParameters)
    edge: EdgeParameters = field(default_factory=EdgeParameters)
    front_relief: ReliefSideParameters = field(default_factory=ReliefSideParameters)
    back_relief: ReliefSideParameters = field(default_factory=lambda: ReliefSideParameters(enabled=False))
    manual_markers: list = field(default_factory=list)
    export_history: list = field(default_factory=list)

    def touch(self):
        """Update the project timestamp."""
        self.updated_at = utc_now_iso()

    def to_dict(self):
        """Serialize to JSON-compatible data."""
        return asdict(self)

    @staticmethod
    def from_dict(data):
        """Create a project from JSON-compatible data."""
        project = MedalProject(name=data.get("name", "Untitled"))
        project.file_version = int(data.get("file_version", PROJECT_FILE_VERSION))
        project.created_at = data.get("created_at", project.created_at)
        project.updated_at = data.get("updated_at", project.updated_at)
        project.same_physical_object = bool(data.get("same_physical_object", True))

        if data.get("front_image"):
            project.front_image = ImageRecord(**data["front_image"])
        if data.get("back_image"):
            project.back_image = ImageRecord(**data["back_image"])
        project.reference_images = [ImageRecord(**item) for item in data.get("reference_images", [])]
        project.outline = OutlineData(**data.get("outline", {}))
        project.dimensions = DimensionParameters(**data.get("dimensions", {}))
        project.edge = EdgeParameters(**data.get("edge", {}))
        project.front_relief = ReliefSideParameters(**data.get("front_relief", {}))
        project.back_relief = ReliefSideParameters(**data.get("back_relief", {"enabled": False}))
        project.manual_markers = [ManualMarker(**item) for item in data.get("manual_markers", [])]
        project.export_history = [ExportRecord(**item) for item in data.get("export_history", [])]
        return project
