# Roadmap

`docs/BASELINE_V1.md` defines completion. A phase is complete only when its automated and recorded manual acceptance evidence exists.

## Phase 0: Engineering baseline

Status: implementation present; successful clean Windows run pending.

Delivered:

- one root Python package and root `pyproject.toml`;
- Python 3.10–3.12 declaration;
- CLI no-argument/help entry points;
- Windows CI configuration for install, imports, critical lint and pytest;
- generic front/back project build wrapper.

Exit gate:

- `python -m pip install -e ".[dev]"` succeeds in a clean Windows environment;
- no-argument CLI, help, GUI import, critical lint and all tests pass on Python 3.10 and 3.12;
- no nested legacy source path can shadow the root package.

## Phase 1: Safe project and image pipeline

Status: core implemented; GUI recovery and schema documentation remain.

Delivered:

- atomic project save with fsync and NaN rejection;
- strict supported project version ceiling;
- safe boolean parsing and malformed-record filtering;
- unique assets and asset-root containment;
- EXIF-aware image loading metadata;
- alpha, contrast, dark and light mask modes;
- mask cleanup and empty-mask build blocking.

Exit gate:

- corrupt and unsupported project files produce readable CLI/GUI errors;
- two same-name assets never overwrite each other;
- stored absolute or `..` paths cannot escape project assets;
- fixed transparent PNG and controlled JPG fixtures produce expected masks.

## Phase 2: Unified coordinates and physical dimensions

Status: core `ImageTransform` implemented; cross-quality fixtures and manual crop UI remain.

Delivered:

- original, crop, resized and final geometry coordinate stages;
- shared point, radius, rectangle and polygon transforms;
- final geometry bbox mapped to requested physical width and height;
- rim millimeter conversion based on the actual final grid;
- transform/downsampling/dimension-error metadata in reports.

Exit gate:

- preview, standard and high outputs remain within ±0.05 mm of requested X/Y size;
- the same marker lands within one final grid cell across quality modes and crop settings;
- manual crop participates in the same transform chain.

## Phase 3: Closed single-side solid

Status: indexed height-field implementation present; complete fixture gate pending.

Delivered:

- shared-index top, base and boundary walls;
- non-uniform adjacent heights without T-junction step walls;
- separate namespaces for disconnected mask components;
- conservative mesh repair;
- edge use, winding, area, signed volume and component diagnostics;
- export blocking for known severe topology errors.

Required fixtures:

- single cell;
- rectangle;
- circle-like mask;
- ring with a hole;
- adjacent unequal heights;
- 2×2 varying heights;
- disconnected fragments;
- border-touching foreground;
- empty mask.

Exit gate for every successful single-side fixture:

- no open, non-manifold or inconsistent-winding edge;
- no invalid index or zero-area face;
- at least one closed oriented component and no inward component;
- expected positive signed volume;
- correct physical dimensions.

## Phase 4: Export and advisory report

Status: format core implemented; Blender evidence and deeper analysis remain.

Delivered:

- shared validation for OBJ, ASCII STL and GLB;
- atomic export with parent-directory creation;
- unique project output paths;
- mirrored back-face winding correction;
- source/mask/crop/resize/height-clipping report metadata;
- explicit `blocked` versus `review_required` manufacturing gate.

Remaining:

- Blender round-trip records for all three formats;
- sample input and output fixtures;
- self-intersection analysis;
- local wall-thickness and minimum-feature checks;
- automatic closed-component orientation repair.

## Phase 5: Complete single-side desktop workflow

Status: partial.

Delivered:

- project new/open/save and image import;
- front parameter controls;
- background build worker and duplicate-build prevention;
- OBJ/STL/GLB actions;
- readable errors and open-output-folder action.

Remaining:

- original image preview;
- exact mask overlay preview;
- heightmap preview;
- manual crop and mask editing;
- local height brush/polygon editing;
- dedicated report/warning panel;
- unsaved-change prompts;
- Windows GUI smoke tests.

Exit gate: a non-technical user completes the full front-image-to-STL flow without a command line.

## Phase 6: Manufacturing-oriented geometry extensions

Status: not complete.

Planned:

- true bevel and rounded-rim geometry;
- constrained sharp height steps;
- local thickness and tiny-feature warnings;
- floating-fragment policy;
- process profiles for print, CNC and mould review;
- optional automatic orientation correction.

These features improve preparation but still do not constitute manufacturing certification.

## Phase 7: Fused double-side model

Status: not implemented. The current placeholder is inspection-only and manufacturing-blocked.

Planned:

- front/back center, scale, rotation and offset alignment;
- clear viewing-direction convention;
- one shared central body;
- no internal overlapping shells or gaps;
- one closed oriented final component;
- final, singular total-thickness semantics.

This phase starts only after the single-side GUI and geometry gates pass.

## Phase 8: Windows delivery

Status: not implemented.

Planned:

- PyInstaller or Nuitka build;
- versioned executable and launch documentation;
- clean Windows machine validation without a development environment;
- known-limitations and manufacturing-disclaimer package;
- preserved CLI diagnostic entry point.

## Phase 9: Optional assistance

Optional AI segmentation or depth suggestions may be evaluated only after the deterministic image, coordinate, topology and engineering gates are stable. AI output must remain editable, local where practical and non-authoritative.
