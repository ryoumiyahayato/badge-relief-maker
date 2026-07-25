# Grayscale-first workflow

The primary deliverable for badge, medal and award artwork is an editable grayscale height master. A shaded 3D preview or mesh is not acceptance evidence for this stage.

## Required order

1. Load and align the source image.
2. Recover the physical silhouette and line-art topology.
3. Accumulate confirmed void/background regions. A later edit must not discard an earlier confirmed void unless the user explicitly reverses it.
4. Reconstruct source contours at the requested master resolution.
5. Export and review the grayscale master.
6. Edit the 16-bit PNG or 32-bit TIFF until its component heights, edges and engraving are accepted.
7. Only after approval, use that exact grayscale master as the source for OBJ/STL/GLB construction.

## Master files

A height-master export produces:

- `height_master_16bit.png`: editable 16-bit unsigned grayscale master;
- `height_master_32bit.tiff`: editable 32-bit floating-point master;
- `height_master_preview.png`: display-only 8-bit preview;
- `linework_mask.png`: separately editable recovered engraving/linework coverage;
- `solid_mask.png`: physical solid footprint;
- `void_mask.png`: cumulative confirmed holes and background gaps;
- `source_aligned.png`: source aligned to the master canvas;
- `height_master_manifest.json`: dimensions, bit depth, applied void regions and processing policy.

The default requested long edge is 8192 pixels. Broad component mass is synthesized on a bounded working grid, then source linework is reconstructed directly at the requested final resolution in memory-bounded strips. This avoids treating a low-resolution 3D mesh grid as the detail ceiling for the grayscale artifact.

## Editing contract

- Black is the lowest or absent height; white is the highest normalized height.
- Confirmed void regions are represented in `void_mask.png` and have zero height in the master.
- Confirmed voids are cumulative. New corrections are applied on top of earlier corrections and cannot silently re-fill an earlier hole.
- Fine source lines are shallow engraving detail, not automatic deep trenches.
- Broad component height and fine engraving are separate signals.
- The exported PNG/TIFF can be edited in a 16-bit/32-bit capable image editor before any mesh is generated.
- Mesh export remains intentionally deferred while the grayscale master is under review.

## Approved-master mesh conversion

After the grayscale master is approved, the strict conversion path is:

```powershell
python -m badge_relief_maker.app `
  --approved-heightmap height_master_16bit.png `
  --approved-solid-mask solid_mask.png `
  --output approved.obj `
  --width-mm 100 `
  --height-mm 150 `
  --base-mm 2.5 `
  --relief-mm 8 `
  --max-grid-cells 1000000
```

This path does not return to the original source image. It does not perform line-art interpretation, automatic embossing or semantic height inference. The approved grayscale is the source of truth. A documented mesh-grid resample may occur when the requested mesh grid exceeds the configured cell limit.

## Limits

A small source image does not contain genuine high-frequency shape information merely because it is enlarged. The exporter preserves and reconstructs the source contour decisions at high resolution, but professional sculptural form still requires region-level correction or manual grayscale editing when the source is ambiguous. The program must expose that uncertainty rather than conceal it with a smooth 3D render.
