"""Authoritative high-resolution grayscale heightmap export.

The grayscale master is a first-class editable artifact. Mesh generation is a
separate downstream consumer and must not be used as the acceptance target for
this stage.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
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
    array = np.asarray(values)
    if array.ndim == 2:
        if int(order) <= 0:
            image = Image.fromarray(array.astype(np.uint8), mode="L")
            resized = image.resize((cols, rows), Image.Resampling.NEAREST)
            return np.asarray(resized, dtype=array.dtype)
        image = Image.fromarray(array.astype(np.float32), mode="F")
        resample = Image.Resampling.BICUBIC if int(order) >= 3 else Image.Resampling.BILINEAR
        return np.asarray(image.resize((cols, rows), resample), dtype=np.float32)
    source_rows, source_cols = array.shape[:2]
    zoom = (rows / max(source_rows, 1), cols / max(source_cols, 1), 1.0)
    return ndi.zoom(array, zoom=zoom, order=int(order), mode="nearest", prefilter=bool(order > 1))


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
    yy, xx = np.nonzero(upsampled)
    if yy.size == 0:
        return np.zeros(target_shape, dtype=bool)
    row0 = max(int(yy.min()) - halo * 2, 0)
    row1 = min(int(yy.max()) + halo * 2 + 1, target_shape[0])
    col0 = max(int(xx.min()) - halo * 2, 0)
    col1 = min(int(xx.max()) + halo * 2 + 1, target_shape[1])
    local_up = upsampled[row0:row1, col0:col1]
    local_light = np.asarray(high_light, dtype=bool)[row0:row1, col0:col1]
    allowed = local_light & ndi.binary_dilation(local_up, iterations=halo)
    labels, count = ndi.label(allowed, structure=np.asarray([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8))
    chosen = np.zeros(local_up.shape, dtype=bool)
    canonical_area = max(int(local_up.sum()), 1)
    for label_id in range(1, int(count) + 1):
        component = labels == label_id
        overlap = int((component & local_up).sum())
        if overlap <= 0:
            continue
        canonical_fraction = overlap / canonical_area
        component_fraction = overlap / max(int(component.sum()), 1)
        if canonical_fraction >= 0.12 or component_fraction >= 0.45:
            chosen |= component
    if not chosen.any():
        chosen = local_up
    chosen &= ndi.binary_dilation(local_up, iterations=halo)
    result = np.zeros(target_shape, dtype=bool)
    result[row0:row1, col0:col1] = chosen
    return result


def _linework_images(rgba, size):
    source = Image.fromarray(np.asarray(rgba, dtype=np.uint8), mode="RGBA").resize(size, Image.Resampling.LANCZOS)
    gray = source.convert("L").filter(ImageFilter.UnsharpMask(radius=1.15, percent=190, threshold=2))
    ink_lut = []
    structural_lut = []
    for value in range(256):
        normalized = value / 255.0
        ink = np.power(np.clip((0.965 - normalized) / 0.62, 0.0, 1.0), 0.72)
        structural = np.clip((0.70 - normalized) / 0.42, 0.0, 1.0)
        ink_lut.append(int(round(ink * 255.0)))
        structural_lut.append(int(round(structural * 255.0)))
    ink = gray.point(ink_lut, mode="L")
    crisp = ink.filter(ImageFilter.GaussianBlur(radius=0.32))
    broad = ink.filter(ImageFilter.GaussianBlur(radius=2.4))
    structural = gray.point(structural_lut, mode="L").filter(ImageFilter.GaussianBlur(radius=0.72))
    return source, ink, crisp, broad, structural


def _promote_master_outputs(
    rgba,
    requested_shape,
    *,
    png16_path,
    tiff32_path,
    preview_path,
    solid_mask_path,
    void_mask_path,
    source_path,
    linework_path,
    engraving_strength,
):
    """Promote a reviewed 4K macro field to an 8K+ master without large RAM spikes.

    The broad component field is resampled from the working master, while source
    line coverage is reconstructed directly at the requested resolution. Processing
    is strip-based and backed by temporary memory maps, so an 8K export does not
    require several full-size float arrays in memory at once.
    """
    rows, cols = requested_shape
    size = (cols, rows)
    base = Image.open(tiff32_path).convert("F").resize(size, Image.Resampling.BICUBIC)
    solid = Image.open(solid_mask_path).convert("L").resize(size, Image.Resampling.NEAREST)
    void = Image.open(void_mask_path).convert("L").resize(size, Image.Resampling.NEAREST)
    source, ink, crisp, broad, structural = _linework_images(rgba, size)

    float_path = tiff32_path.with_suffix(".working-f32")
    uint16_path = png16_path.with_suffix(".working-u16")
    preview_work_path = preview_path.with_suffix(".working-u8")
    height_mm = np.memmap(float_path, dtype=np.float32, mode="w+", shape=(rows, cols))
    height_u16 = np.memmap(uint16_path, dtype=np.uint16, mode="w+", shape=(rows, cols))
    height_preview = np.memmap(preview_work_path, dtype=np.uint8, mode="w+", shape=(rows, cols))
    strength = float(np.clip(engraving_strength, 0.0, 0.08))
    strip = 256
    for row0 in range(0, rows, strip):
        row1 = min(row0 + strip, rows)
        box = (0, row0, cols, row1)
        base_values = np.asarray(base.crop(box), dtype=np.float32)
        mask_values = np.asarray(solid.crop(box), dtype=np.uint8) >= 128
        crisp_values = np.asarray(crisp.crop(box), dtype=np.float32) / 255.0
        broad_values = np.asarray(broad.crop(box), dtype=np.float32) / 255.0
        structural_values = np.asarray(structural.crop(box), dtype=np.float32) / 255.0
        engraving = np.clip(0.82 * crisp_values + 0.12 * broad_values + 0.18 * structural_values, 0.0, 1.0)
        values = np.where(mask_values, np.clip(base_values - strength * engraving, 0.0, 1.0), 0.0).astype(np.float32)
        height_mm[row0:row1] = values
        height_u16[row0:row1] = np.round(values * 65535.0).astype(np.uint16)
        height_preview[row0:row1] = np.round(np.power(values, 0.86) * 255.0).astype(np.uint8)
    height_mm.flush()
    height_u16.flush()
    height_preview.flush()

    Image.fromarray(height_mm, mode="F").save(tiff32_path)
    Image.fromarray(height_u16, mode="I;16").save(png16_path)
    Image.fromarray(height_preview, mode="L").save(preview_path)
    solid.save(solid_mask_path)
    void.save(void_mask_path)
    source.save(source_path)
    ink.save(linework_path)

    minimum = float(height_mm[height_mm > 0].min()) if np.any(height_mm > 0) else 0.0
    maximum = float(height_mm.max()) if height_mm.size else 0.0
    del height_mm, height_u16, height_preview
    for path in (float_path, uint16_path, preview_work_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    for image in (base, solid, void, source, ink, crisp, broad, structural):
        image.close()
    return minimum, maximum


def export_prepared_heightmap_master(
    prepared,
    output_dir,
    *,
    long_edge_px=8192,
    lineart_region_overrides=(),
    source_native_size=None,
    engraving_strength=0.028,
):
    """Export 16-bit PNG and 32-bit TIFF height masters from a prepared field."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    requested_shape = _target_shape(prepared.heightmap.shape, long_edge_px)
    synthesis_long_edge = min(int(long_edge_px), 4096)
    target_shape = _target_shape(prepared.heightmap.shape, synthesis_long_edge)
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

    gray_image = Image.fromarray(rgba_master, mode="RGBA").convert("L")
    gray_image = gray_image.filter(ImageFilter.UnsharpMask(radius=1.15, percent=190, threshold=2))
    gray = np.asarray(gray_image, dtype=np.float32) / 255.0
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

    ink_coverage = np.power(np.clip((0.965 - gray) / 0.62, 0.0, 1.0), 0.72) * master_mask
    crisp_ink = ndi.gaussian_filter(ink_coverage, sigma=0.32)
    broad_ink = ndi.gaussian_filter(ink_coverage, sigma=2.4)
    structural_core = np.clip((0.70 - gray) / 0.42, 0.0, 1.0) * master_mask
    structural_core = ndi.gaussian_filter(structural_core, sigma=0.72)
    engraving = np.clip(0.82 * crisp_ink + 0.12 * broad_ink + 0.18 * structural_core, 0.0, 1.0)
    strength = float(np.clip(engraving_strength, 0.0, 0.08))
    working_strength = 0.0 if requested_shape != target_shape else strength
    height = macro - working_strength * engraving

    weights = master_mask.astype(np.float32)
    numerator = ndi.gaussian_filter(height * weights, sigma=0.22, mode="constant")
    denominator = ndi.gaussian_filter(weights, sigma=0.22, mode="constant")
    smoothed = np.divide(numerator, denominator, out=height.copy(), where=denominator > 1e-7)
    height = np.where(master_mask, np.clip(0.985 * height + 0.015 * smoothed, 0.0, 1.0), 0.0).astype(np.float32)

    png16_path = output_dir / "height_master_16bit.png"
    tiff32_path = output_dir / "height_master_32bit.tiff"
    preview_path = output_dir / "height_master_preview.png"
    solid_mask_path = output_dir / "solid_mask.png"
    void_mask_path = output_dir / "void_mask.png"
    source_path = output_dir / "source_aligned.png"
    linework_path = output_dir / "linework_mask.png"
    manifest_path = output_dir / "height_master_manifest.json"

    Image.fromarray(np.round(height * 65535.0).astype(np.uint16)).save(png16_path)
    Image.fromarray(height, mode="F").save(tiff32_path)
    Image.fromarray(np.round(np.power(np.clip(height, 0.0, 1.0), 0.86) * 255.0).astype(np.uint8), mode="L").save(preview_path)
    Image.fromarray((master_mask * 255).astype(np.uint8), mode="L").save(solid_mask_path)
    Image.fromarray((void_mask * 255).astype(np.uint8), mode="L").save(void_mask_path)
    Image.fromarray(rgba_master, mode="RGBA").save(source_path)
    Image.fromarray(np.round(np.clip(ink_coverage, 0.0, 1.0) * 255.0).astype(np.uint8), mode="L").save(linework_path)

    normalized_min = float(height[master_mask].min()) if master_mask.any() else 0.0
    normalized_max = float(height[master_mask].max()) if master_mask.any() else 0.0
    if requested_shape != target_shape:
        normalized_min, normalized_max = _promote_master_outputs(
            prepared.rgba,
            requested_shape,
            png16_path=png16_path,
            tiff32_path=tiff32_path,
            preview_path=preview_path,
            solid_mask_path=solid_mask_path,
            void_mask_path=void_mask_path,
            source_path=source_path,
            linework_path=linework_path,
            engraving_strength=strength,
        )
        target_rows, target_cols = requested_shape

    manifest = {
        "artifact_role": "authoritative editable grayscale height master",
        "mesh_generation_deferred": True,
        "void_region_policy": "cumulative union; later exports must not discard earlier confirmed voids",
        "linework_policy": "source contours are reconstructed at master resolution and remain editable separately",
        "width_px": int(target_cols),
        "height_px": int(target_rows),
        "bit_depth_png": 16,
        "bit_depth_tiff": 32,
        "black_value": 0,
        "white_value": 65535,
        "source_native_size_px": list(source_native_size or prepared.rgba.shape[1::-1]),
        "canonical_processing_size_px": [int(prepared.rgba.shape[1]), int(prepared.rgba.shape[0])],
        "normalized_height_min": normalized_min,
        "normalized_height_max": normalized_max,
        "synthesis_long_edge_px": int(synthesis_long_edge),
        "final_linework_reconstructed_at_requested_resolution": True,
        "applied_void_regions": applied_voids,
        "skipped_void_regions": skipped_voids,
        "files": {
            "height_master_16bit_png": png16_path.name,
            "height_master_32bit_tiff": tiff32_path.name,
            "preview": preview_path.name,
            "solid_mask": solid_mask_path.name,
            "void_mask": void_mask_path.name,
            "source_aligned": source_path.name,
            "linework_mask": linework_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
