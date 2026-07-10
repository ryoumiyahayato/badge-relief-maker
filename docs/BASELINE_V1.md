# Badge Relief Maker v1 Baseline

## Product definition

Badge Relief Maker is a Windows-first, local and offline 2.5D relief base-model generator for badges, medals, crests, plaques, nameplates and similar decorative objects.

The product converts one front image, or project-managed front and back images, into an editable rough mesh intended for later Blender refinement. The target is to automate roughly 60%–80% of repetitive outline, base, coarse-height and export work. It is not a general image-to-3D system and does not promise an automatically production-ready replica.

## Source of truth

This document is the v1 development and acceptance baseline. Feature status is determined by automated acceptance tests and recorded manual validation, not by the existence of a module or button.

Related records:

- `docs/PROJECT_FORMAT.md`: `.medalproj` schema and trust boundary.
- `docs/VALIDATION_RECORD.md`: pending Windows, Blender, slicer, CAM and physical validation evidence.
- `docs/CODEX_TASKS.md`: ordered implementation work.
- `docs/ROADMAP.md`: acceptance-driven delivery phases.

The supported source root is the repository root `badge_relief_maker/` package. The obsolete nested placeholder source tree is not a supported runtime path.

## Architecture baseline

```text
CLI / PySide6 GUI
        |
        v
Project service and validated .medalproj model
        |
        v
EXIF-aware image loader -> foreground mask -> mask cleanup
        |
        v
ImageTransform
(original -> crop -> resized grid -> geometry crop -> millimeters)
        |
        v
masked foreground height normalization -> manual marker edits -> rim boost
        |
        v
closed indexed height-field solid -> conservative repair
        |
        v
manufacturing advisory report -> atomic OBJ/STL/GLB export
```

Core architectural rules:

1. Image coordinates and dimensions must pass through one `ImageTransform` record.
2. Markers are applied in the final tight geometry grid; processed coordinates are shifted by the final geometry crop and `final` coordinates are not.
3. Processing padding and grid density must not change requested physical dimensions.
4. Project files and imported assets are untrusted input.
5. A mesh report may block severe topology errors but never certifies manufacturing safety.
6. The double-side placeholder remains a non-fused inspection output and is always manufacturing-blocked.
7. The deterministic local pipeline must remain usable without AI, cloud services or a high-end GPU.

## Current reviewed implementation status

| Area | Status | Notes |
|---|---|---|
| Root package and CLI | Implemented, CI verification pending | Generic side wrapper restored; no-argument and help entry points are in the Windows quality gate. |
| Project create/save/load | Implemented with remaining migration work | Atomic save, strict version ceiling, boolean parsing, unique assets/exports and asset-root containment are present. Formal migration from a later supported version is not yet needed or implemented. |
| PNG alpha mask | Implemented | Auto mode only trusts alpha when it contains useful variation. |
| Opaque JPG/PNG mask | Implemented for controlled backgrounds | Contrast, explicit dark-foreground and explicit light-foreground modes are present. Perspective correction and arbitrary photographic segmentation are not implemented. |
| EXIF orientation | Implemented | The loader records original/oriented sizes and orientation metadata. |
| Unified coordinate transform | Implemented for crop/resize/final-geometry marker mapping | Manual user crop UI and millimeter-space editing are still pending. |
| Foreground-only height normalization | Implemented | A uniform foreground deterministically becomes full normalized height before optional inversion. |
| Manual height markers | Implemented core | Set/add/subtract with circle, rectangle and polygon shapes; visual editing UI remains pending. |
| Single-side indexed solid | Implemented for tested mask cases | Closed shared-index height field, positive component volumes and requested XY size are required by regression tests. Self-intersection and local-thickness checks remain pending. |
| OBJ/STL/GLB | Implemented | Shared array validation, atomic replacement and automatic parent-directory creation are present. Blender round-trip evidence is still pending. |
| Manufacturing report | Advisory implementation | Open/non-manifold/winding/invalid/zero-area/component orientation checks and an explicit non-certifying gate are present. Thin walls, self-intersections and process-specific checks are missing. |
| Desktop GUI | Partial | Project operations, persisted core parameters, background build worker, three export formats and readable errors are present. Image/mask/height previews and full editing remain pending. |
| Double-side mode | Preview only | Two separately closed objects are mirrored and exported for inspection. They are not aligned or fused into one production solid. |
| Windows launcher | Development launcher only | `run_windows.bat` starts the installed GUI and is not packaging. |
| Windows packaging | Not implemented | PyInstaller/Nuitka executable and clean-machine verification remain pending. |

## Required acceptance gates

### Engineering gate

```powershell
python -m pip install -e ".[dev]"
python -m badge_relief_maker.app
python -m badge_relief_maker.app --help
python -m ruff check badge_relief_maker tests
python -m pytest -q
```

All commands must succeed on supported Windows Python 3.10 and 3.12 environments. The initial Ruff gate is intentionally limited to execution-breaking syntax/name defects; broader formatting enforcement requires a dedicated repository-wide normalization change.

### Single-side geometry gate

Representative inputs must include a single cell, rectangle, circle-like mask, ring with a hole, adjacent unequal heights, a 2×2 varying height field, disconnected fragments, border-touching foreground and an empty mask.

A successful exported single-side model must satisfy:

- finite `N×3` vertices and integer triangular faces;
- valid indices and zero zero-area faces after repair;
- `boundary_edge_count == 0`;
- `non_manifold_edge_count == 0`;
- `inconsistent_winding_edge_count == 0`;
- at least one closed oriented component;
- no inward closed component;
- positive signed volume for expected outward components;
- requested X/Y dimensions within 0.05 mm;
- empty masks are blocked before model export.

The repository now includes generated single-side fixture tests for single-cell, rectangular, ring, varying-height, disconnected and border-touching masks, plus cross-quality physical-size checks. Full CI execution evidence is still pending.

### Export gate

OBJ, STL and GLB must be written atomically, use unique project export names and import successfully in Blender with correct dimensions and outward normals. STL coordinates use millimeters by convention because STL does not store units.

Manual evidence belongs in `docs/VALIDATION_RECORD.md`. Pending fields are not a pass.

### GUI gate

The final single-side GUI acceptance flow is:

```text
new project
-> import transparent PNG or controlled JPG
-> inspect source, mask and heightmap previews
-> set width, height, base, relief, mask, quality and rim parameters
-> generate in a worker thread
-> inspect report and warnings
-> export OBJ/STL/GLB
-> open output directory
```

The current GUI does not yet meet the complete preview/editing portion of this gate.

## Thickness semantics

- `base_thickness_mm` is the flat base depth of one generated side.
- A single-side output bbox thickness is the base plus the generated relief/rim height actually present in the mesh.
- `total_thickness_mm` is currently a double-side body/spacing budget. The non-fused placeholder uses it only to position two complete side solids.
- A future fused double-side model must define whether total thickness includes both reliefs before that output can be considered production-capable.

## Manufacturing disclaimer

Closed and consistently oriented geometry is necessary but not sufficient for manufacturing. The current report does not detect all self-intersections, local thin walls, minimum line widths, inaccessible CNC regions, overhangs, mould draft constraints or material/process limits. Every successful report remains `review_required`; severe known geometry errors produce `blocked`.

## Deferred work order

1. Obtain and fix a clean Windows full-suite result.
2. Record Blender import results for OBJ, STL and GLB and add stable sample artifacts where appropriate.
3. Add manual crop and source/mask/heightmap preview editing.
4. Add local wall-thickness, tiny-feature and floating-fragment analysis.
5. Add self-intersection detection and component-level orientation repair.
6. Add true bevelled/rounded rim geometry.
7. Complete single-side GUI acceptance.
8. Implement front/back alignment and a fused central body.
9. Build and verify a Windows executable on a clean machine.
10. Consider optional AI assistance only after the deterministic acceptance gates pass.
