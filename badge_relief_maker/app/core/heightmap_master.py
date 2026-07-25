"""Authoritative high-resolution grayscale heightmap export.

The grayscale master is a first-class editable artifact. Mesh generation is a
separate downstream consumer and must not be used as the acceptance target for
this stage.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from .lineart_region_graph import analyze_lineart_regions
from .mask_generator import foreground_mask


def _target_shape(shape, long_edge_px):
    rows, cols = [int(value) for value in shape]
    long_edge = int(long_edge_px)
    if long_edge < 256:
        raise ValueError("long_edge_px must be at least 256")
    scale = float(long_edge) / float(max(rows, cols, 1))
    return max(1, int(round(rows * scale))), max(1, int(round(cols * scale)))


def _resize_array(values, target_shape, order):
    rows, cols = target_shape
    source_rows, source_cols = values.shape[:2]
    zoom = (rows / max(source_rows, 1), cols / max(source_cols, 1))
    if values.ndim == 3:
        zoom = zoom + (1.0,)
    return ndi.zoom(values, zoom=zoom, order=int(order), mode="nearest", prefilter=bool(order > 1))


def _canonical_region_map(rgba):
    canonical_mask, _ = foreground_mask(rgba, mode="auto", alpha_threshold=1, luminance_threshold=20)
    labels, report = analyze_lineart_regions(rgba, canonical_mask)
    return canonical_mask, labels, report


def _refine_region_at_master_resolution(low_region, high_light, target_shape):
    """Refine a canonical region against high-resolution line boundaries.

    The canonical mask is authoritative. A local halo lets antialiased source
    contours replace blocky nearest-neighbour edges without allowing a broken scan
    line to flood into an unrelated part of the emblem.
    """
    upsampled = _resize_array(np.asarray(low_region, dtype=np.uint8), target_shape, order=0).astype(bool)
    scale = max(target_shape[0] / max(low_region.shape[0], 1), target_shape[1] / max(low_region.shape[1], 1))
    halo = max(4, int(round(2.2 * scale)))
    allowed = np.asarray(high_light, dtype=bool) & ndi.binary_dilation(upsampled, iterations=halo)
    labels, count = ndi.label(allowed, structure=np.asarray([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8))
    chosen = np.zeros(target_shape, dtype=bool)
    canonical_area = max(int(upsampled.sum()), 1)
    for label_id in range(1, int(count) + 1):
        component = labels == label_id
        overlap = int((component & upsampled).sum())
        if overlap <= 0:
            continue
        canonical_fraction = overlap / canonical_area
        component_fraction = overlap / max(int(component.sum()), 1)
        if canonical_fraction >= 0.12 or component_fraction >= 0.45:
            chosen |= component
    if not chosen.any():
        chosen = upsampled
    return chosen & ndi.binary_dilation(upsampled, iterations=halo)


def export_prepared_heightmap_master(
    prepared,
    output_dir,
    *,
    long_edge_px=8192,
    lineart_region_overrides=(),
    source_native_size=None,
    engraving_strength=0.012,
):
    """Export 16-bit PNG and 32-bit TIFF height masters from a prepared field."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    target_shape = _target_shape(prepared.heightmap.shape, long_edge_px)
    target_rows, target_cols = target_shape
    rgba_master = np.asarray(
        Image.fromarray(np.asarray(prepared.rgba, dtype=np.uint8), mode="RGBA").resize(
            (target_cols, target_rows), Image.Resampling.LANCZOS
        )
    )

    overall_mask, _ = foreground_mask(rgba_master, mode="auto", alpha_threshold=1, luminance_threshold=20)
    canonical_mask, canonical_labels, canonical_report = _canonical_region_map(prepared.rgba)
    del canonical_mask
    regions_by_display = {int(item["display_id"]): item for item in canonical_report.get("regions", [])}

    rgb = rgba_master[:, :, :3].astype(np.float32) / 255.0
    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    high_light = (gray >= 0.86) & overall_mask

    void_mask = np.zeros(target_shape, dtype=bool)
    applied_voids = []
    skipped_voids = []
    for raw in lineart_region_overrides or ():
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role", raw.get("operation", "surface"))).strip().lower()
        if role not in {"background", "hole", "void"}:
            continue
        try:
            display_id = int(raw.get("display_id"))
        except (TypeError, ValueError):
            skipped_voids.append({"display_id": raw.get("display_id"), "reason": "invalid display id"})
            continue
        region_info = regions_by_display.get(display_id)
        if region_info is None:
            skipped_voids.append({"display_id": display_id, "reason": "canonical region not found"})
            continue
        canonical_region = canonical_labels == int(region_info["region_id"])
        refined = _refine_region_at_master_resolution(canonical_region, high_light, target_shape)
        void_mask |= refined
        applied_voids.append(
            {
                "display_id": display_id,
                "canonical_pixel_count": int(canonical_region.sum()),
                "master_pixel_count": int(refined.sum()),
            }
        )

    master_mask = overall_mask & ~void_mask
    macro = _resize_array(np.asarray(prepared.heightmap, dtype=np.float32), target_shape, order=3)
    macro = np.clip(macro, 0.0, 1.0)
    macro_blur = ndi.gaussian_filter(macro, sigma=2.0)
    macro = np.clip(macro + 0.24 * (macro - macro_blur), 0.0, 1.0)

    # Re-sample source linework at master resolution. It remains shallow engraving;
    # broad component height still comes from the reviewed macro field.
    ink = np.clip((0.94 - gray) / 0.94, 0.0, 1.0) * master_mask
    broad_ink = ndi.gaussian_filter(ink, sigma=7.0)
    fine_ink = np.clip(ink - 0.76 * broad_ink, 0.0, 1.0)
    structural_ink = ndi.gaussian_filter(np.clip((0.68 - gray) / 0.68, 0.0, 1.0) * master_mask, sigma=0.85)
    strength = float(np.clip(engraving_strength, 0.0, 0.08))
    height = macro - strength * fine_ink - strength * 0.67 * structural_ink

    weights = master_mask.astype(np.float32)
    numerator = ndi.gaussian_filter(height * weights, sigma=0.38, mode="constant")
    denominator = ndi.gaussian_filter(weights, sigma=0.38, mode="constant")
    smoothed = np.divide(numerator, denominator, out=height.copy(), where=denominator > 1e-7)
    height = np.where(master_mask, np.clip(0.95 * height + 0.05 * smoothed, 0.0, 1.0), 0.0).astype(np.float32)

    png16_path = output_dir / "height_master_16bit.png"
    tiff32_path = output_dir / "height_master_32bit.tiff"
    preview_path = output_dir / "height_master_preview.png"
    solid_mask_path = output_dir / "solid_mask.png"
    void_mask_path = output_dir / "void_mask.png"
    source_path = output_dir / "source_aligned.png"
    manifest_path = output_dir / "height_master_manifest.json"

    Image.fromarray(np.round(height * 65535.0).astype(np.uint16)).save(png16_path)
    Image.fromarray(height, mode="F").save(tiff32_path)
    Image.fromarray(np.round(np.power(np.clip(height, 0.0, 1.0), 0.86) * 255.0).astype(np.uint8), mode="L").save(preview_path)
    Image.fromarray((master_mask * 255).astype(np.uint8), mode="L").save(solid_mask_path)
    Image.fromarray((void_mask * 255).astype(np.uint8), mode="L").save(void_mask_path)
    Image.fromarray(rgba_master, mode="RGBA").save(source_path)

    manifest = {
        "artifact_role": "authoritative editable grayscale height master",
        "mesh_generation_deferred": True,
        "width_px": int(target_cols),
        "height_px": int(target_rows),
        "bit_depth_png": 16,
        "bit_depth_tiff": 32,
        "black_value": 0,
        "white_value": 65535,
        "source_native_size_px": list(source_native_size or prepared.rgba.shape[1::-1]),
        "canonical_processing_size_px": [int(prepared.rgba.shape[1]), int(prepared.rgba.shape[0])],
        "normalized_height_min": float(height[master_mask].min()) if master_mask.any() else 0.0,
        "normalized_height_max": float(height[master_mask].max()) if master_mask.any() else 0.0,
        "applied_void_regions": applied_voids,
        "skipped_void_regions": skipped_voids,
        "files": {
            "height_master_16bit_png": png16_path.name,
            "height_master_32bit_tiff": tiff32_path.name,
            "preview": preview_path.name,
            "solid_mask": solid_mask_path.name,
            "void_mask": void_mask_path.name,
            "source_aligned": source_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
