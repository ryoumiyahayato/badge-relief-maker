# Badge Relief Maker v1 Acceptance Baseline

## Product definition

Badge Relief Maker is a Windows-first, local and offline 2.5D relief base-model generator for badges, medals, crests, plaques, nameplates and similar decorative objects.

It automates much of the repetitive mask, outline, backing, coarse-height, alignment and export work before manual Blender or manufacturing-tool refinement. It is not a general image-to-3D system and does not promise an automatically production-ready replica.

## Acceptance rule

This document remains the v1 product acceptance contract even though the persisted project format is now version 2. A feature is accepted only when its automated gate passes on the current commit and any required external evidence is recorded. A module, field, button or previous test run is not sufficient by itself.

Related records:

- `docs/PROJECT_FORMAT.md`: `.medalproj` v2 schema and trust boundary.
- `docs/VALIDATION_RECORD.md`: Windows, Blender, slicer, CAM and physical evidence.
- `docs/CODEX_TASKS.md`: remaining execution work.
- `docs/ROADMAP.md`: delivery phases.

## Architecture candidate

```text
CLI / coordinate-safe PySide6 editor
        |
        v
validated .medalproj v2 service
        |
        v
EXIF load -> perspective -> source mask edits -> manual/automatic crop
        |
        v
ImageTransform
(source -> crop -> resized grid -> final grid -> millimeters)
        |
        v
foreground height -> layers/locks -> local brushes -> rim/refinement
        |
        v
closed single-side solid OR aligned fused double-side solid
        |
        v
repair/orientation -> advisory manufacturing analysis
        |
        v
atomic OBJ/STL/GLB export -> Windows package candidate
```

Architectural rules:

1. Image coordinates and physical dimensions pass through one `ImageTransform`.
2. Mask edits are persisted in source space; final-grid height/layer edits use `final_normalized` coordinates.
3. Processing padding and quality density cannot change requested physical X/Y dimensions.
4. Project files, imported paths and mesh arrays are untrusted input.
5. The manufacturing gate may block known defects but never certifies safety.
6. The inspection placeholder remains separate from the fused double-side mode and is always blocked.
7. The deterministic pipeline must remain usable without cloud services, AI or a high-end GPU.

## Current reviewed implementation state

| Area | Implementation state | Acceptance state |
|---|---|---|
| Root package and CLI | Implemented | Latest Windows CI run still required |
| Project v2 and migration | Implemented | Automated regression required on latest commit |
| Atomic save/path containment/unique assets | Implemented | Automated regression required |
| EXIF and alpha/luminance masks | Implemented | Representative image fixtures required in final gate |
| Perspective/manual crop/mask edits | Implemented core and GUI interaction | Latest GUI tests and manual interaction record required |
| Unified coordinates | Implemented, including reversible final-grid mapping | Cross-quality marker fixture gate required |
| Height generation and editing | Grayscale, layers, locks, set/add/subtract/smooth, global refine implemented | Latest full-suite result required |
| Single-side closed solid | Implemented for current fixtures | Latest topology suite required |
| Profiled edges | Straight, sloped, bevel and rounded builders implemented | Blender/mesh visual evidence required |
| Manufacturing diagnostics | Topology, orientation, self-intersection broad phase, local vertical thickness, feature and process-direction estimates implemented | Advisory only; slicer/CAM/physical checks remain external |
| OBJ/STL/GLB | Atomic export and programmatic reload checks implemented | Blender manual import record pending |
| Desktop GUI | Source/mask/height previews, crop, mask, layer and height tools, report, worker and unsaved handling implemented | Latest Windows GUI smoke/manual flow pending |
| Double-side | Fused shared-body mode and separate blocked placeholder implemented | Representative alignment and Blender validation pending |
| Windows packaging | PyInstaller spec/script and CI artifact job implemented | Clean-machine executable result pending |

## Required engineering gate

```powershell
python -m pip install -e ".[dev]"
python -m badge_relief_maker.app
python -m badge_relief_maker.app --help
python -c "from badge_relief_maker.app.ui.editor_window import MainWindow; print(MainWindow.__name__)"
python -m ruff check badge_relief_maker tests
python -m pytest -q
```

The commands must pass on Windows Python 3.10 and 3.12 for the same commit. The package job must additionally build and smoke-test `dist/BadgeReliefMaker.exe` on Windows Python 3.12.

A previously reported intermediate Python 3.12 run passed installation, CLI, GUI import and Ruff, and reached 168 passing regression tests before the final GUI/coordinate continuation. That historical result is not a pass for the current commit.

## Single-side geometry gate

Required representative cases:

- single cell;
- rectangle;
- circle-like footprint;
- ring with a hole;
- adjacent unequal heights;
- 2×2 varying heights;
- disconnected fragments;
- border-touching foreground;
- empty mask;
- layered sharp plateaus;
- straight, sloped, bevel and rounded edges.

Each successful single-side mesh must have:

- finite `N×3` vertices;
- triangular integer faces with valid indices;
- zero zero-area faces after repair;
- `boundary_edge_count == 0`;
- `non_manifold_edge_count == 0`;
- `inconsistent_winding_edge_count == 0`;
- at least one closed oriented component;
- no inward closed component;
- positive signed volume for outward components;
- requested X/Y dimensions within `0.05 mm`;
- no export when the final mask is empty.

## Coordinate and GUI gate

The final single-side GUI flow is:

```text
new project
-> import transparent PNG or controlled JPG
-> inspect source, exact final mask and heightmap
-> optionally set perspective and crop
-> add/remove mask regions
-> add layer or height edits
-> set dimensions, relief, quality, rim, edge and process parameters
-> build in a worker thread
-> inspect report and warnings
-> export OBJ/STL/GLB
-> open output directory
```

Specific coordinate requirements:

- perspective points use the EXIF-oriented source;
- manual crop uses the post-perspective source grid;
- final mask clicks are converted back to source pixels before persistence;
- final height/layer clicks use final-grid normalized coordinates;
- preview/standard/high preserve the same physical edit location within one final grid cell;
- changing perspective cannot silently retain stale crop/mask/height coordinates;
- all mutable project controls are disabled during a background build.

## Double-side gate

The fused candidate must:

- process front and back independently before alignment;
- support viewed-back horizontal flip, scale, rotation and X/Y offset;
- resample both fields to one physical grid;
- generate one shared central body rather than two overlapping bases;
- contain exactly one closed oriented final component;
- have zero boundary and non-manifold edges;
- preserve outward winding;
- define `total_thickness_mm` as central body thickness excluding outward relief;
- remain distinct from the inspection placeholder.

`base_thickness_mm` is a single-side setting. It does not impose a lower bound on fused central-body thickness. The old two-base rule applies only to the non-fused placeholder.

## Export gate

OBJ, STL and GLB must:

- share finite array and index validation;
- write through temporary files and atomic replacement;
- create parent directories;
- use unique project filenames;
- reload through the programmatic validation helper;
- import into Blender with expected dimensions, object count and outward normals.

STL coordinates use millimeters by convention because STL does not declare units.

## Manufacturing interpretation

A closed mesh is necessary but not sufficient for manufacturing. Current automated analysis remains approximate:

- triangle self-intersection uses a bounded spatial broad phase;
- local wall analysis is primarily vertical/height-field based;
- minimum feature size is estimated from the sampled footprint;
- process analysis is orientation based and does not simulate a slicer, cutter, mould flow or draft in full.

Every non-blocked result remains `review_required`. Manual Blender, slicer, CAM and physical evidence remains mandatory for a production claim.

## Remaining acceptance work

1. Obtain a clean current-commit Windows Python 3.10/3.12 quality-gate result.
2. Build and run the packaged executable on a clean Windows machine.
3. Record Blender imports for OBJ, STL and GLB, including fused double-side output.
4. Record representative slicer and CAM results.
5. Verify cross-quality visual-edit placement with fixed fixtures.
6. Validate profiled edges and alignment on representative artwork.
7. Produce and measure at least one physical sample before making process-tolerance claims.
8. Continue improving self-intersection completeness and true local-thickness analysis where external results expose defects.
