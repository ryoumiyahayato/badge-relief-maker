# Badge Relief Maker

Badge Relief Maker is a Windows-first, local and offline tool that converts badge, medal, crest, plaque, nameplate and similar artwork into an editable 2.5D relief base mesh.

The intended result is a rough model for later Blender, printing, CNC or mould-design refinement. It is not a general image-to-3D system and does not claim to generate an automatically production-ready object.

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

## Current deterministic pipeline

The current single-side path performs:

1. EXIF-aware JPG/PNG loading.
2. Optional normalized four-point perspective rectification.
3. `auto`, `alpha`, `luminance`, `luminance-dark` or `luminance-light` foreground masking.
4. Source-space manual mask additions/removals.
5. Optional manual crop, component cleanup, hole filling and mask smoothing.
6. Foreground-only grayscale height normalization with a defined uniform-brightness policy.
7. Processing crop and quality-dependent grid resize.
8. A recorded `ImageTransform` through source, crop, resized grid, final geometry crop and millimeters.
9. Region layers, local locks and circle/rectangle/polygon height edits.
10. Set, add, subtract and mask-aware smooth brush operations.
11. Optional global smoothing and detail sharpening.
12. Millimeter-aware rim height processing.
13. Shared-index closed single-side or fused double-side mesh construction.
14. Straight, sloped, bevelled or rounded boundary profiles.
15. Conservative face cleanup and component orientation repair.
16. Advisory topology, self-intersection, feature-size, thickness and process-direction analysis.
17. Atomic OBJ, STL or GLB export.

Processing padding and grid density do not define the finished physical size. The final foreground bounding box is scaled to the requested X/Y dimensions.

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
- `--height-mode grayscale|layers|hybrid`
- `--smooth-strength 0..1`
- `--detail-sharpness 0..1`
- `--rim-width-mm` and `--rim-height-mm`
- `--edge-style straight|sloped|bevel|rounded`
- `--process-profile general|fdm|resin|cnc|mould`

## Project workflow

```powershell
python -m badge_relief_maker.app --new-project "Test Medal" --project-path test.medalproj
python -m badge_relief_maker.app --project-path test.medalproj --import-front front.png
python -m badge_relief_maker.app --project-path test.medalproj --import-back back.png
python -m badge_relief_maker.app --project-path test.medalproj --build-front --project-export-format obj --quality standard
python -m badge_relief_maker.app --project-path test.medalproj --build-double --project-export-format glb --quality standard
```

Project format version 2 persists:

- front/back/reference assets;
- physical dimensions and separate single-side base/fused-body thickness semantics;
- mask, crop, perspective and quality settings;
- mask edits, region layers and height markers;
- rim and boundary-profile parameters;
- front/back alignment parameters;
- manufacturing-process profile;
- export history and reports.

Version 1 projects are migrated in memory to version 2. Unsupported newer versions remain blocked. Project JSON and mesh files are written through temporary files and atomic replacement, imported assets are uniquely named, and stored asset paths must remain inside the project asset directory.

## Visual editor coordinate model

The GUI distinguishes two editing surfaces:

- **Source preview:** perspective selection uses the EXIF-oriented source; crop and source-space edits use the post-perspective source.
- **Final mask/height previews:** clicks use `final_normalized` coordinates tied to the exact tight geometry grid.

Final-grid mask clicks are transformed back to source pixels before persistence because mask edits are applied before crop and resize. Height and layer brushes remain in final-grid normalized coordinates. Changing perspective requires clearing coordinate-dependent crop, mask, layer and height edits rather than silently drifting them.

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

Current external acceptance still pending:

1. A clean run of the latest commit on Windows Python 3.10 and 3.12.
2. Blender import records for OBJ, STL and GLB.
3. Slicer and CAM records using representative fixtures.
4. A clean-machine packaged executable test.
5. Physical print/CNC measurements and process-specific tolerances.

Brightness is only a visual proxy for depth. Fine text, lines and decorative details may disappear during sampling or fail in the selected manufacturing process, so manual refinement remains part of the intended workflow.
