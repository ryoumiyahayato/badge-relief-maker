"""Shared option catalogs used by models, adapters, CLI and GUI layers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OptionCatalog:
    """One ordered set of supported string values with normalization aliases."""

    values: tuple[str, ...]
    default: str
    aliases: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if not self.values:
            raise ValueError("an option catalog must contain at least one value")
        if self.default not in self.values:
            raise ValueError("an option catalog default must be one of its values")
        if any(target not in self.values for _, target in self.aliases):
            raise ValueError("option aliases must resolve to supported values")

    def __contains__(self, value):
        return str(value).strip().lower() in self.values

    def normalize(self, value):
        normalized = str(value or self.default).strip().lower()
        normalized = dict(self.aliases).get(normalized, normalized)
        return normalized if normalized in self.values else self.default


SIDE_NAMES = OptionCatalog(("front", "back"), "front")
MASK_MODES = OptionCatalog(("auto", "alpha", "luminance", "luminance-dark", "luminance-light"), "auto")
HEIGHT_MODES = OptionCatalog(("grayscale", "layers", "hybrid"), "grayscale")
QUALITY_MODES = OptionCatalog(
    ("preview", "standard", "high"),
    "standard",
    aliases=(("low", "preview"), ("draft", "preview"), ("hi", "high"), ("export", "high"), ("high_quality", "high")),
)
PROCESS_PROFILES = OptionCatalog(("general", "fdm", "resin", "cnc", "mould"), "general")
EDGE_STYLES = OptionCatalog(("straight", "sloped", "bevel", "rounded"), "straight")
RIM_PROFILES = OptionCatalog(("flat", "linear", "smooth"), "flat")
FOOTPRINT_MODES = OptionCatalog(("union", "intersection", "front", "back"), "union")
EXPORT_FORMATS = OptionCatalog(("obj", "stl", "glb"), "obj")
