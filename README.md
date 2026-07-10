# Badge Relief Maker

Badge Relief Maker is an experimental Windows-first, local and offline tool for converting badge, medal, crest, plaque, nameplate and similar artwork into an editable 2.5D relief base mesh.

The intended result is a rough model that completes much of the repetitive outline, base, coarse-height and export work before manual refinement in Blender. It is not a general image-to-3D system and does not claim to generate an automatically production-ready model.

The reviewed development and acceptance baseline is in [`docs/BASELINE_V1.md`](docs/BASELINE_V1.md).

## Installation

The repository root is the only supported package root. Python 3.10–3.12 is supported.

```powershell
python -m pip install -e ".[dev]"
python -m badge_relief_maker.app
python -m badge_relief_maker.app --help
python -m ruff check badge_relief_maker tests
python -m pytest -q
```

Install only the runtime core:

```powershell
python -m pip install -e .
```

Install the optional desktop GUI:

```powershell
python -m pip install -e ".[gui]"
python -m badge_relief_maker.app --gui
```

The obsolete nested placeholder source tree is not a supported runtime path.

## Current single-side pipeline

The current deterministic path performs these steps:

1. Load JPG or PNG and apply EXIF orientation.
2. Record source format, original size, oriented size and whether the source had alpha.
3. Generate a foreground mask using `auto`, `alpha`, `luminance`, `luminance-dark` or `luminance-light`.
4. Remove small components, fill configured small holes and optionally smooth the mask.
5. Block the build when the cleaned mask is empty.
6. Normalize grayscale height only from masked foreground pixels.
7. Crop and downsample the processing grid when required.
8. Record one `ImageTransform` for original image, processing crop, resized grid, final geometry crop and millimeter conversion.
9. Transform circle, rectangle and polygon markers into the final geometry grid.
10. Apply set, add or subtract height edits.
11. Convert requested rim width from millimeters using the actual final grid.
12. Build a shared-index closed height-field solid with a flat base and boundary walls.
13. Run conservative face and unreferenced-vertex cleanup.
14. Generate topology, winding, volume, component and advisory manufacturing reports.
15. Atomically export OBJ, ASCII STL or binary GLB.

Processing padding and quality-grid density do not define the finished physical size. For a masked build, the final foreground bounding box is scaled to the requested width and height.

The indexed top surface averages incident cell heights at shared corners. This favors a continuous closed surface over the former independent-pixel plateaus and T-junction-prone step walls. A future constrained-height mode is required for truly sharp internal steps.

## Direct image build

```powershell
python -m badge_relief_maker.app `
  --input input.jpg `
  --output output.obj `
  --width-mm 80 `
  --height-mm 60 `
  --base-mm 2 `
  --relief-mm 3 `
  --mask-mode auto `
  --preview-dir previews
```

Use an explicit polarity for a controlled opaque background:

```powershell
# Dark artwork on a light border/background
python -m badge_relief_maker.app --input dark-on-light.jpg --output model.stl --mask-mode luminance-dark

# Light artwork on a dark border/background
python -m badge_relief_maker.app --input light-on-dark.jpg --output model.glb --mask-mode luminance-light
```

Use alpha explicitly for a prepared transparent PNG:

```powershell
python -m badge_relief_maker.app --input artwork.png --output artwork.glb --mask-mode alpha
```

A simple heightmap rim can be requested in pixels or millimeters:

```powershell
python -m badge_relief_maker.app `
  --input artwork.png `
  --output artwork.obj `
  --rim-width-mm 2 `
  --rim-height-mm 0.8 `
  --rim-profile smooth
```

If the rim boost exceeds the configured relief-height range, the report records clipped pixels and adds a warning.

## Project files

A `.medalproj` stores:

- name, file version and timestamps;
- front, back and reference image records;
- whether the two faces belong to the same physical object;
- width, height, total-thickness budget and one-side base thickness;
- front/back mask, crop, invert, quality and relief settings;
- outline and edge/rim settings;
- manual height markers;
- export history and reports.

Project handling includes:

- strict rejection of unsupported newer file versions;
- explicit boolean parsing instead of `bool("false")`;
- malformed nested-record filtering;
- JSON serialization with NaN/Infinity rejection;
- temporary-file write, flush, fsync and atomic replacement;
- sanitized and unique imported asset names;
- containment checks requiring stored image paths to remain inside the project asset root;
- unique export names so old history entries are not silently overwritten.

Create and populate a project:

```powershell
python -m badge_relief_maker.app --new-project "Test Medal" --project-path test.medalproj
python -m badge_relief_maker.app --project-path test.medalproj --import-front front.png
python -m badge_relief_maker.app --project-path test.medalproj --import-back back.png
python -m badge_relief_maker.app --project-path test.medalproj --import-reference reference.jpg --reference-role same_type_front
```

Build one side:

```powershell
python -m badge_relief_maker.app --project-path test.medalproj --build-front --project-export-format obj --quality preview
python -m badge_relief_maker.app --project-path test.medalproj --build-side back --project-export-format glb --quality standard
```

Project front/back settings now persist mask mode, thresholds, invert, minimum-thickness warning, crop settings, quality and relief height, and are passed to the core build.

## Coordinate model

Manual geometry uses one recorded chain:

```text
EXIF-oriented original image
-> processing crop
-> resized processing grid
-> tight geometry crop
-> millimeter mesh
```

Original normalized coordinates are relative to the EXIF-oriented source. Original pixel coordinates, processed-grid coordinates and final-geometry coordinates are distinguished. Marker centers, radii, rectangle dimensions and polygon points are transformed consistently.

Supported marker operations are set, add and subtract. Supported shapes are circle/brush, rectangle and polygon/freeform.

## Export and manufacturing report

OBJ, STL and GLB share finite `N×3` vertex validation, triangular integer face validation and index-range checks. Exports create missing parent directories and replace target files atomically. STL coordinates are written in millimeters by convention; STL itself contains no unit metadata.

The report includes:

- vertex and face counts;
- X/Y/Z bounding box and requested-size error;
- edge closure, non-manifold and winding diagnostics;
- invalid and zero-area face counts;
- whole-mesh and per-component signed volume;
- disconnected-component counts and orientation;
- mask, crop, resize, source and EXIF metadata;
- downsampling and rim-height clipping state;
- export path, format and unit convention;
- an explicit manufacturing gate.

The gate is `blocked` for known severe geometry defects. Otherwise it remains `review_required`. It never recommends unattended manufacturing because self-intersections, local wall thickness, minimum feature size and process-specific tool access are not yet fully checked.

## GUI status

The PySide6 GUI currently provides project creation/open/save, image import, persisted core parameters, worker-thread builds, OBJ/STL/GLB actions, readable error messages and opening the output folder.

It is still incomplete against the v1 acceptance baseline. Source-image, exact mask and heightmap visual previews, manual crop/mask editing, a dedicated report panel and unsaved-change prompts remain to be implemented.

## Double-side status

The current double-side command produces a non-fused inspection placeholder. It builds two complete single-side solids, mirrors the back mesh, reverses its triangle winding and exports named front/back objects where supported.

It is explicitly manufacturing-blocked. It is not the future aligned, shared-body, single-component double-side model.

## Known limitations

Direct manufacturing output is not recommended without Blender, slicer or CAM inspection. Important missing work includes:

1. Full Windows CI evidence and clean-machine installation verification.
2. Fixed image/mesh fixtures and recorded Blender import checks.
3. Self-intersection detection and automatic component orientation repair.
4. Local wall-thickness, tiny-feature and process-specific manufacturability checks.
5. True bevelled or rounded rim geometry.
6. Source/mask/heightmap visual editing and manual crop.
7. A fused and aligned double-side central body.
8. Windows executable packaging.
9. Physical print or CNC tolerance validation.

Brightness is only a visual proxy for relief depth. Users must retain the ability to adjust height manually, and every manufacturing report is advisory rather than certification.
