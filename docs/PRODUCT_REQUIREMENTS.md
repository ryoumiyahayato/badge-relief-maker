# Product Requirements

`docs/BASELINE_V1.md` is the acceptance source of truth for implementation status and release decisions.

## Product goal

Build a Windows local/offline desktop tool that converts 2D artwork for badges, medals, crests, plaques, nameplates and similar decorative objects into an editable rough 2.5D relief base mesh.

The product should automate approximately 60%–80% of repetitive preparation work: foreground extraction, outline/base generation, coarse grayscale height, simple local height corrections, closure checks and OBJ/STL/GLB export. Users are expected to refine artistic detail and prepare the model for a specific manufacturing process in Blender or another specialist tool.

## Product promise

The product may promise:

- deterministic local processing;
- transparent PNG and controlled-background JPG/PNG support;
- explicit physical width, height, base and relief controls;
- an editable closed single-side base mesh for accepted inputs;
- project persistence and later back-image addition;
- advisory topology and manufacturing warnings;
- Blender-oriented OBJ/GLB and millimeter-coordinate STL output.

The product must not promise:

- recovery of true physical depth from image brightness;
- automatic reconstruction of unseen side geometry;
- a production-ready result without inspection;
- universal print, CNC, mould, casting or stamping safety;
- a fused double-side model while only the placeholder path exists;
- generic AI image-to-complete-3D reconstruction.

## Target users

- artists preparing relief base meshes for Blender;
- small workshops producing decorative prints, carvings or mould masters;
- users digitizing simple flat or shallow-relief artwork;
- operators who need repeatable local/offline preprocessing rather than cloud reconstruction.

## Functional requirements

### Projects

Users must be able to create, save, open and continue a `.medalproj`. A project stores front/back/reference images, dimensions, mask and height settings, edge/rim settings, manual markers, quality mode and export history.

Project files are untrusted input. The application must reject invalid future versions, malformed JSON, non-finite values and resource paths outside the project asset root. Saving and exporting must avoid silent overwrite.

### Input images and masks

The minimum supported image paths are:

- prepared transparent PNG;
- opaque PNG/JPG on a controlled light or dark background.

Supported mask choices are alpha, contrast luminance, explicit dark foreground, explicit light foreground and auto selection. EXIF orientation must be applied before coordinates are interpreted.

An empty cleaned mask is a blocking error. Mask cleanup and downsampling must be recorded in the build report.

### Coordinates and dimensions

All crop, resize, final geometry crop and marker operations must use one recorded coordinate chain. Quality mode may change grid density but must not change requested physical size.

For accepted single-side fixtures, output X/Y size must be within ±0.05 mm of the requested dimensions. Circle radius, rectangle size and polygon points must transform consistently.

### Heightmap and local edits

The first version uses grayscale height normalized only from foreground pixels. Mask background RGB must not affect height range. Invert, set, add and subtract operations are required. Circle, rectangle and polygon regions are required.

Brightness is only a visual approximation of relief depth. Manual correction must remain possible.

### Single-side solid

A successful single-side export must contain a flat base, relief top, complete side walls and consistently outward closed geometry. The checked mesh must have:

- finite `N×3` vertices;
- triangular integer faces with valid indices;
- zero boundary edges;
- zero non-manifold edges;
- zero inconsistent shared-edge winding;
- zero zero-area faces;
- at least one closed oriented component;
- no inward closed component.

Known severe topology failures must block export.

### Export and report

OBJ, STL and GLB are required. The three formats must share mesh validation and atomic target replacement. Project exports must receive unique names.

The report must include dimensions, edge/winding diagnostics, face validity, components, signed volumes, mask/crop/resize metadata, clipping/downsampling state, export path/format and a manufacturing disclaimer.

A successful checked mesh is `review_required`, not certified safe. A known severe defect is `blocked`. The application must never state that unattended manufacturing is recommended.

### Desktop GUI

The single-side GUI must eventually support project operations, front-image import, source/mask/heightmap previews, parameter controls, background generation, export selection, report/warning display and opening the output directory.

Core builds must not block the UI thread. Errors must be shown in user-readable form. The current GUI is partial until visual preview/editing and unsaved-change handling are completed.

### Double-side mode

The current placeholder may be retained for inspection, provided it remains clearly named and manufacturing-blocked.

A complete double-side feature requires manual alignment, one shared central body, no internal shell overlap/gap, one final closed component and a singular definition of total thickness. It must not be counted as complete before those conditions pass.

### Windows delivery

The final deliverable requires a versioned Windows executable built with PyInstaller or Nuitka and tested on a clean machine without a Python development environment. CLI diagnostics must remain available.

## Non-functional requirements

- Local and offline by default.
- Ordinary Windows laptop friendly.
- Deterministic output for equal inputs and parameters.
- No hidden cloud or AI dependency.
- Clear failure messages rather than raw tracebacks in normal CLI/GUI use.
- Atomic project and mesh writes.
- Automated Windows checks on Python 3.10 and 3.12 during development.
- Documentation status based on acceptance evidence, not module existence.

## Known non-goals for v1

- generic character or mechanical reconstruction;
- arbitrary photogrammetry;
- highly reflective or transparent object reconstruction;
- automatic engraving-depth truth from grayscale;
- manufacturing certification;
- fused double-side production output before the single-side gate is complete;
- early AI integration that bypasses unresolved coordinate or topology work.
