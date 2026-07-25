# Badge Relief Maker

Badge Relief Maker is a Windows-first, local and offline tool for turning badge, medal, crest, plaque, nameplate and similar artwork into an editable grayscale height master and, only after that master is approved, a downstream 2.5D relief mesh.

The current acceptance artifact is the exported grayscale master—not the shaded 3D preview and not the OBJ/STL/GLB. The grayscale-first contract is documented in [`docs/GRAYSCALE_FIRST_WORKFLOW.md`](docs/GRAYSCALE_FIRST_WORKFLOW.md).

The intended mesh result remains a base model for later Blender, printing, CNC or mould-design refinement. It is not a general image-to-3D system and does not claim to generate an automatically production-ready object.

The acceptance contract is [`docs/BASELINE_V1.md`](docs/BASELINE_V1.md). Manual Windows, Blender, slicer, CAM and physical evidence belongs in [`docs/VALIDATION_RECORD.md`](docs/VALIDATION_RECORD.md).

## Install and verify

Python 3.10–3.12 is supported. The repository root is the only supported package root.

```powershell
python -m pip install -e ".[dev]"
python -m badge_relief_maker.app
python -m badge_relief_maker.app --help
python -m ruff check badge_relief_maker tests
python -m pytest -q
```

Launch the desktop editor:

```powershell
python -m badge_relief_maker.app --gui
```

Build a Windows executable:

```powershell
./build_windows.ps1
```

The script installs the packaging extra, builds `dist/BadgeReliefMaker.exe` with PyInstaller and smoke-tests its `--help` entry point. GitHub Actions also contains a Windows 3.12 packaging job that uploads the executable when the complete Windows quality gate passes. Opening the packaged application without command-line arguments launches the GUI; explicit arguments retain the diagnostic CLI.

## Grayscale-master export

The editor provides `Front 16-bit Heightmap` and `Back 16-bit Heightmap` actions. The command-line equivalent is:

```powershell
python -m badge_relief_maker.app `
  --project-path test.medalproj `
  --export-front-heightmap `
  --heightmap-long-edge-px 8192 `
  --heightmap-output-dir heightmaps/front
```

The export produces:

- `height_master_16bit.png`;
- `height_master_32bit.tiff`;
- `height_master_preview.png`;
- `linework_mask.png`;
- `solid_mask.png`;
- `void_mask.png`;
- `source_aligned.png`;
- `height_master_manifest.json`.

Confirmed void/background regions are accumulated by union. A later export does not discard an earlier confirmed hole unless the project data explicitly reverses that decision. Broad component mass is synthesized on a bounded working grid, while source contours and engraving coverage are reconstructed directly at the requested final resolution. Mesh generation remains deferred during this review stage.

## Build only from an approved grayscale master

After the PNG/TIFF master is approved, generate a mesh from that exact artifact:

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

This strict path does not return to the original image and does not run automatic embossing or line-art inference. The approved grayscale is the source of truth. Mesh-grid resampling is reported when the approved master exceeds the configured grid-cell limit.

## Current deterministic pipeline

The current single-side path performs:

1. EXIF-aware JPG/PNG loading.
2. Optional normalized four-point perspective rectification.
3. `auto`, `background`, `alpha`, `luminance`, `luminance-dark` or `luminance-light` foreground masking. `auto` preserves enclosed pale artwork by removing only background-like pixels connected to the image border.
4. Source-space manual mask additions/removals.
5. Optional manual crop, component cleanup, hole filling and mask smoothing.
6. `emboss`, `flat`, `grayscale`, `layers` or `hybrid` height generation.
7. `emboss` separates two conservative interpretations:
   - continuous-tone photographs and shaded artwork use robust luminance plus multiscale detail;
   - achromatic line drawings receive a broad silhouette relief. Thick contours remain structural grooves while fine hatching is much shallower. Enclosed white regions remain neutral and are never raised merely because they are closed.
8. Line-art regions separated by ink are reported as unresolved until their roles are confirmed. The editor can assign an entire selected region as `background`, `surface`, `raise` or `recess`.
9. Processing crop and quality-dependent grid resize.
10. A recorded `ImageTransform` through source, crop, resized grid, final geometry crop and millimeters.
11. Feathered region layers, local locks and circle/rectangle/ellipse/annulus/polygon height edits. Rounded profiles create broad component mass without flattening all source engraving.
12. Set, add, subtract and mask-aware smooth brush operations. Smoothing excludes background and true-void pixels instead of bleeding across physical boundaries.
13. Optional global smoothing and detail sharpening.
14. Millimeter-aware rim height processing.
15. High-resolution 16-bit PNG and 32-bit TIFF grayscale-master export for visual review and editing.
16. After grayscale approval, shared-index closed single-side or fused double-side mesh construction, including local corner-sector splitting around checkerboard void contacts.
17. Straight, sloped, bevelled or rounded boundary profiles.
18. Conservative face cleanup and component orientation repair.
19. Advisory topology, self-intersection, feature-size, thickness and process-direction analysis.
20. Atomic OBJ, STL or GLB export.

Processing padding and grid density do not define the finished physical size. The final foreground bounding box is scaled to the requested X/Y dimensions.

## Visual preview and masking

The desktop editor shows four distinct views:

- the source artwork;
- the exact final silhouette overlay;
- a numbered, colour-coded line-art topology and region-role pane;
- a shaded relief preview.

The shaded relief preview is diagnostic only. It cannot replace review of the exported 16-bit/32-bit grayscale master.

For opaque badge artwork on a plain background, leave mask mode on `auto`. The editor will use border-connected background removal when that recovers enclosed white or pale regions that a simple luminance threshold would otherwise punch out as holes.

For line drawings, the summary reports unresolved regions and the preview directory includes the numbered region map. Use `region background`, `region surface`, `region raise` or `region recess` on the topology pane. `background` removes the whole selected region from the physical footprint; the other three roles place it relative to its carrier surface. These confirmations are persisted in the project.

`emboss` is the recommended automatic starting point. `flat` creates a uniform plaque for manual layer editing, while `grayscale` retains literal brightness-to-depth behaviour for images whose brightness genuinely represents height.

## Direct image build

```powershell
python -m badge_relief_maker.app `
  --input input.png `
  --output output.stl `
  --width-mm 80 `
  --height-mm 60 `
  --base-mm 2 `
  --relief-mm 3 `
  --mask-mode auto `
  --edge-style rounded `
  --radius-mm 0.8 `
  --process-profile resin `
  --preview-dir previews
```

Useful options include:

- `--manual-crop-box X0 Y0 X1 Y1`
- `--height-mode emboss|flat|grayscale|layers|hybrid`
- `--smooth-strength 0..1`
- `--detail-sharpness 0..1`
- `--rim-width-mm` and `--rim-height-mm`
- `--edge-style straight|sloped|bevel|rounded`
- `--process-profile general|fdm|resin|cnc|mould`

## Project workflow

```powershell
python -m badge_relief_maker.app --new-project "Test Medal" --project-path test.medalproj
python -m badge_relief_maker.app --project-path test.medalproj --import-front front.png
python -m badge_relief_maker.app --project-path test.medalproj --export-front-heightmap --heightmap-long-edge-px 8192
# Review and edit the PNG/TIFF master before continuing.
python -m badge_relief_maker.app --approved-heightmap height_master_16bit.png --approved-solid-mask solid_mask.png --output approved.obj
```

Project format version 2 persists:

- front/back/reference assets;
- physical dimensions and separate single-side base/fused-body thickness semantics;
- mask, crop, perspective and quality settings;
- mask edits, region layers, explicit line-art region roles and height markers;
- rim and boundary-profile parameters;
- front/back alignment parameters;
- manufacturing-process profile;
- export history and reports.

Version 1 projects are migrated in memory to version 2. Unsupported newer versions remain blocked. Project JSON and mesh files are written through temporary files and atomic replacement, imported assets are uniquely named, and stored asset paths must remain inside the project asset directory.

## Visual editor coordinate model

The GUI distinguishes two editing surfaces:

- **Source preview:** perspective selection uses the EXIF-oriented source; crop and source-space edits use the post-perspective source.
- **Final mask/topology/height previews:** clicks use `final_normalized` coordinates tied to the exact tight geometry grid.

Final-grid mask clicks are transformed back to source pixels before persistence because mask edits are applied before crop and resize. Height, layer and line-art region selections remain in final-grid normalized coordinates. Changing perspective requires clearing coordinate-dependent crop, mask, region, layer and height edits rather than silently drifting them.

The editor can copy a completed project-owned export into a user-selected output folder. Existing filenames receive stable `_2`, `_3`, and later suffixes; history is changed only after the external copy succeeds, and the project-owned source export remains recorded in the report as a recovery path.

All mutable controls, including export-folder controls, are disabled while a background build reads the project.

## Double-side modes

Two deliberately different operations remain available:

- **Inspection placeholder:** two independent complete side solids; always manufacturing-blocked.
- **Fused double-side:** front/back fields are resampled to a common grid, the viewed back is optionally flipped and manually scaled/rotated/offset, and one shared central body is generated.

For fused output, `total_thickness_mm` means central body thickness and excludes outward front/back relief. It is independent of `base_thickness_mm`, which is used only by single-side and placeholder workflows. Fused output requires one connected aligned footprint and one closed final component.

A two-sided build uses one quality mode for both fields. An explicit build quality overrides the two saved values; without an override, saved front/back quality modes must normalize to the same mode. A fused model also requires one common process profile because it represents one physical object.

## Reports and limits

The report includes dimensions, topology, winding, zero-area faces, component orientation and volume, crop/resize metadata, self-intersection analysis state, local vertical-thickness estimates, footprint feature estimates, tiny disconnected components and orientation-based process warnings.

A result is either `blocked` or `review_required`; it is never certified safe for unattended manufacturing. Automated checks do not replace Blender, slicer, CAM, mould-draft or physical tolerance validation.

Brightness alone is not physical depth. Black-and-white line art also does not unambiguously state whether a closed region is a surface, foreground component, shadow or hole. The automatic line-art path therefore avoids inventing local domes and requires explicit region confirmation for ambiguous structure.

The current system remains a general grayscale height-master and 2.5D bas-relief base-model generator, not an automatic professional sculptor. Exact object ordering, undercuts, hidden surfaces and fully semantic multi-part modelling still require region confirmation, manual grayscale refinement or a future learned depth/normal inference stage.

## Editable master model

After the grayscale master is approved, a single-side OBJ export is a real closed 3D solid. Its front follows the approved relief field, its back is an automatically generated flat plane, and the boundary is closed by side walls. The OBJ keeps one shared vertex pool and names three face groups: `front_relief`, `side_wall`, and `flat_back`.

This makes the same complete model easier to continue editing in Blender, 3ds Max, Maya, ZBrush and other OBJ-compatible tools. STL remains the manufacturing/printing mesh, while GLB remains the compact interchange and viewing format.
