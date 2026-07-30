"""Image loading and preprocessing helpers."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True)
class LoadedImage:
    """RGBA pixels plus source metadata needed for deterministic processing."""

    rgba: np.ndarray
    source_path: str
    source_format: str | None
    source_mode: str
    original_size: tuple[int, int]
    oriented_size: tuple[int, int]
    had_alpha: bool
    exif_orientation: int | None
    exif_transposed: bool

    def report(self):
        return {
            "source_path": self.source_path,
            "source_format": self.source_format,
            "source_mode": self.source_mode,
            "original_size_xy": list(self.original_size),
            "oriented_size_xy": list(self.oriented_size),
            "had_alpha": bool(self.had_alpha),
            "exif_orientation": self.exif_orientation,
            "exif_transposed": bool(self.exif_transposed),
        }


def load_image(path: str | Path) -> LoadedImage:
    """Load an image, apply EXIF orientation and return RGBA pixels with metadata."""
    source_path = Path(path)
    with Image.open(source_path) as image:
        source_format = image.format
        source_mode = image.mode
        original_size = tuple(image.size)
        bands = image.getbands()
        had_alpha = "A" in bands or "transparency" in image.info
        try:
            orientation = image.getexif().get(274)
        except (AttributeError, TypeError, ValueError):
            orientation = None
        oriented = ImageOps.exif_transpose(image)
        oriented_size = tuple(oriented.size)
        rgba = np.asarray(oriented.convert("RGBA"))
    return LoadedImage(
        rgba=rgba,
        source_path=str(source_path),
        source_format=source_format,
        source_mode=source_mode,
        original_size=original_size,
        oriented_size=oriented_size,
        had_alpha=bool(had_alpha),
        exif_orientation=int(orientation) if orientation is not None else None,
        exif_transposed=bool(orientation not in {None, 1}),
    )
def normalize_alpha_background(image: np.ndarray, threshold: int = 5) -> np.ndarray:
    """Set near-transparent alpha values to zero."""
    image = np.asarray(image)
    if image.ndim != 3 or image.shape[2] != 4:
        raise ValueError("expected rgba image")
    result = image.copy()
    alpha = result[:, :, 3]
    alpha[alpha <= int(threshold)] = 0
    result[:, :, 3] = alpha
    return result
