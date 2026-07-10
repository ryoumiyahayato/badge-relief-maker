"""Project data model for medal relief projects."""

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone


PROJECT_FILE_VERSION = 1


def utc_now_iso():
    """Return a stable UTC timestamp string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dataclass_from_dict(model_type, data, **defaults):
    """Create a dataclass instance while ignoring unknown saved fields."""
    raw = dict(defaults)
    if isinstance(data, dict):
        raw.update(data)
    allowed = {item.name for item in fields(model_type)}
    return model_type(**{key: value for key, value in raw.items() if key in allowed})


def _optional_dataclass_from_dict(model_type, data, *required_keys, **defaults):
    if not isinstance(data, dict):
        return None
    if any(key not in data for key in required_keys):
        return None
    return _dataclass_from_dict(model_type, data, **defaults)


def _dict_list(value):
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0", ""}:
            return False
    return bool(default)


def _coerce_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _manual_marker_from_dict(data):
    marker = _optional_dataclass_from_dict(ManualMarker, data, "marker_type", "target")
    if marker is None:
        return None
    if not isinstance(marker.data, dict):
        marker.data = {}
    return marker


def _export_record_from_dict(data):
    record = _optional_dataclass_from_dict(ExportRecord, data, "path", "export_format")
    if record is not None and not isinstance(record.report, dict):
        record.report = {}
    return record


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
        if not isinstance(data, dict):
            data = {}
        project = MedalProject(name=str(data.get("name", "Untitled")))
        project.file_version = _coerce_int(data.get("file_version", PROJECT_FILE_VERSION), PROJECT_FILE_VERSION)
        project.created_at = data.get("created_at", project.created_at)
        project.updated_at = data.get("updated_at", project.updated_at)
        project.same_physical_object = _coerce_bool(data.get("same_physical_object", True), True)

        project.front_image = _optional_dataclass_from_dict(ImageRecord, data.get("front_image"), "role", "path")
        project.back_image = _optional_dataclass_from_dict(ImageRecord, data.get("back_image"), "role", "path")
        project.reference_images = [
            item
            for item in (
                _optional_dataclass_from_dict(ImageRecord, item, "role", "path")
                for item in _dict_list(data.get("reference_images", []))
            )
            if item is not None
        ]
        project.outline = _dataclass_from_dict(OutlineData, data.get("outline", {}))
        project.dimensions = _dataclass_from_dict(DimensionParameters, data.get("dimensions", {}))
        project.edge = _dataclass_from_dict(EdgeParameters, data.get("edge", {}))
        project.front_relief = _dataclass_from_dict(ReliefSideParameters, data.get("front_relief", {}))
        project.back_relief = _dataclass_from_dict(ReliefSideParameters, data.get("back_relief", {}), enabled=False)
        project.manual_markers = [
            item
            for item in (_manual_marker_from_dict(item) for item in _dict_list(data.get("manual_markers", [])))
            if item is not None
        ]
        project.export_history = [
            item
            for item in (_export_record_from_dict(item) for item in _dict_list(data.get("export_history", [])))
            if item is not None
        ]

        for image in [project.front_image, project.back_image, *project.reference_images]:
            if image is not None:
                image.is_reference = _coerce_bool(image.is_reference, False)
                if not isinstance(image.preprocessing, dict):
                    image.preprocessing = {}
        project.outline.manually_edited = _coerce_bool(project.outline.manually_edited, False)
        if not isinstance(project.outline.points, list):
            project.outline.points = []
        project.edge.rim_enabled = _coerce_bool(project.edge.rim_enabled, False)
        project.edge.use_smoothed_side_walls = _coerce_bool(project.edge.use_smoothed_side_walls, False)
        project.front_relief.enabled = _coerce_bool(project.front_relief.enabled, True)
        project.back_relief.enabled = _coerce_bool(project.back_relief.enabled, False)
        return project
