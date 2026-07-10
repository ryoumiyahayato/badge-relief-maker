# Roadmap

`docs/BASELINE_V1.md` defines acceptance. Implementation present is not the same as accepted; current-commit CI and required external records must exist before a phase is closed.

## Phase 0: Engineering baseline

Status: **implementation complete, current CI evidence pending**.

Present:

- one root Python package and root `pyproject.toml`;
- Python 3.10–3.12 support declaration;
- CLI no-argument/help entry points;
- Windows Python 3.10/3.12 install, GUI import, Ruff and pytest workflow;
- Windows Python 3.12 PyInstaller artifact job;
- no supported nested legacy source root.

Exit gate: the current commit passes both Windows quality jobs and the package job.

## Phase 1: Safe project and image pipeline

Status: **implementation complete, fixture acceptance pending**.

Present:

- `.medalproj` v2 with v1 migration;
- atomic save, fsync and NaN/Infinity rejection;
- safe boolean parsing and malformed-record filtering;
- unique assets/exports and asset-root containment;
- EXIF-aware loading;
- alpha and controlled-background luminance mask modes;
- normalized perspective rectification;
- source-space mask edits and manual crop;
- cleanup and empty-mask blocking.

Exit gate: fixed transparent, dark-on-light and light-on-dark fixtures plus corrupt/unsafe project fixtures pass on the current commit.

## Phase 2: Coordinates and physical dimensions

Status: **core implementation complete, cross-quality visual fixture pending**.

Present:

- source, crop, resized and final geometry stages;
- forward and reverse final-grid point/radius mapping;
- source-space mask edits;
- `final_normalized` height/layer edits;
- circle, rectangle and polygon transforms;
- requested foreground X/Y dimensions independent of processing padding;
- millimeter rim conversion on the final grid.

Exit gate: the same source and final-preview edits land within one final cell across preview, standard and high quality while X/Y stay within ±0.05 mm.

## Phase 3: Single-side geometry

Status: **implementation candidate complete, current topology gate pending**.

Present:

- shared-index continuous height fields;
- exact layered plateaus;
- flat base and closed boundary walls;
- straight, sloped, bevel and rounded profiles;
- disconnected-component namespaces;
- conservative cleanup and outward orientation repair;
- direct open/non-manifold/winding/area/volume/component checks;
- export blocking for known severe defects.

Exit gate: all required single-cell, rectangle, circle, ring, varying-height, disconnected, border, empty, layered and edge-profile fixtures pass.

## Phase 4: Export and advisory manufacturing report

Status: **implementation candidate complete, external import evidence pending**.

Present:

- atomic OBJ, ASCII STL and GLB export;
- common finite-array/index validation;
- unique project output names;
- trimesh programmatic reload checks;
- topology and component orientation reports;
- bounded spatial self-intersection analysis;
- local vertical-thickness and footprint feature estimates;
- tiny-component and orientation-based process warnings;
- explicit `blocked` versus `review_required` gate.

Exit gate: current automated tests pass and Blender imports for all formats are recorded. Slicer/CAM checks remain separate external gates.

## Phase 5: Single-side desktop workflow

Status: **implementation candidate complete, Windows interaction record pending**.

Present:

- new/open/save and front/back/reference import;
- front/back parameter switching;
- source, exact final mask and heightmap previews;
- perspective quadrilateral and manual crop;
- mask add/remove, height and layer brushes;
- final-grid coordinate-safe persistence;
- report and log panels;
- unsaved-change prompt;
- worker-thread builds with all mutable controls frozen;
- OBJ/STL/GLB and open-output-folder actions.

Exit gate: a non-technical user completes the documented front-image-to-STL flow on a clean Windows machine without command-line intervention.

## Phase 6: Fused double-side geometry

Status: **implementation candidate complete, alignment/external validation pending**.

Present:

- independent front/back preprocessing;
- viewed-back horizontal flip;
- scale, rotation and X/Y offset controls;
- union/intersection/front/back footprint modes;
- common physical grid;
- one shared central body with outward relief on both sides;
- one-component requirement and topology gate;
- central-body thickness semantics independent of single-side base thickness;
- old two-object placeholder retained and explicitly blocked.

Exit gate: representative asymmetric front/back artwork aligns correctly, produces one closed component and imports correctly into Blender/slicer.

## Phase 7: Windows delivery

Status: **build configuration complete, clean-machine validation pending**.

Present:

- PyInstaller entry and spec;
- `build_windows.ps1`;
- executable `--help` smoke test;
- CI artifact upload configuration;
- preserved CLI diagnostics.

Exit gate: artifact builds from the current commit and launches on a Windows machine without Python or development dependencies.

## Phase 8: External process validation

Status: **not complete**.

Required:

- Blender dimensions, normals, object count and edit-mode records;
- slicer shell/repair/unsupported-feature records;
- CAM open-surface and tool-access records;
- at least one measured physical print or CNC sample;
- documented process-specific tolerances and failure modes.

Automated checks remain advisory until this phase provides evidence.

## Phase 9: Optional assistance

Optional AI segmentation or depth suggestions may be evaluated only after the deterministic gates are stable. Assistance must remain editable, non-authoritative and local where practical.
