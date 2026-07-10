# Codex Tasks

This file is the execution guide for future automated coding work. `docs/BASELINE_V1.md` is the acceptance source of truth.

Do not turn this project into a general AI image-to-3D application. Preserve the deterministic local relief pipeline and fix correctness, coordinates, topology and engineering stability before adding optional AI.

## Working rule for every task

1. Audit the affected existing code for obvious regressions first.
2. Fix blockers before adding features.
3. Add or update tests for every core behavior change.
4. Do not mark a feature complete until its acceptance tests pass.
5. Keep all processing local and offline.
6. Keep the double-side placeholder explicitly non-fused and manufacturing-blocked.

## Task 0: Windows quality gate

Status: implemented in workflow; successful run evidence pending.

Required commands:

```powershell
python -m pip install -e ".[dev]"
python -m badge_relief_maker.app
python -m badge_relief_maker.app --help
python -m ruff check badge_relief_maker tests
python -m pytest -q
```

Acceptance:

- Python 3.10 and 3.12 pass on Windows.
- Package and GUI modules import from the repository root package.
- No obsolete nested package is used.
- Record the actual result in `docs/VALIDATION_RECORD.md`.

The initial Ruff gate intentionally checks execution-breaking syntax/name defects. Enable broad formatting/import-order rules only in a dedicated normalization change.

## Task 1: Project format and resource safety

Status: core implemented; migration and GUI recovery tests pending.

Implemented:

- Atomic JSON replacement with flush/fsync and NaN/Infinity rejection.
- Strict supported file-version ceiling.
- Explicit boolean parsing.
- Malformed nested-record filtering.
- Unique imported asset names and export names.
- Asset-root containment checks.
- Persisted front/back image-processing settings.
- Schema and trust-boundary documentation in `docs/PROJECT_FORMAT.md`.
- Single-side builds validate only the requested face; double-side builds validate both.

Next acceptance work:

- Add formal migration when version 2 is introduced.
- Add GUI tests for corrupt JSON and unsupported versions.
- Add validation for more malformed field types during load, not only before build.

## Task 2: Input image and mask pipeline

Status: controlled-image MVP implemented.

Implemented:

- EXIF-aware loading and source metadata.
- Alpha, contrast luminance, dark-foreground and light-foreground modes.
- Auto mode only trusts alpha when it contains variation.
- Mask cleanup, preview files, crop and downsampling.
- Empty masks block model export.

Next:

- Manual crop UI.
- User-editable mask input.
- Preview overlay showing the exact final mask.
- Perspective correction for photographed paper drawings.

## Task 3: Unified coordinates

Status: core transform implemented.

Implemented:

- `ImageTransform` records original, crop, resized and final geometry stages.
- Circle, rectangle and polygon markers use the same transform.
- Pixel radii and rectangular dimensions scale with resize.
- Original/processed marker positions are shifted into the final tight geometry grid.
- `coordinate_space: final` remains relative to the final geometry grid.
- Processing padding does not change final requested XY dimensions.

Next:

- Use `ImageTransform` directly in GUI preview hit testing.
- Add physical millimeter editing and manual crop transforms.
- Verify marker location across preview/standard/high fixtures within one final grid cell.

## Task 4: Heightmap and local edits

Status: grayscale and marker core implemented.

Implemented:

- Foreground-only grayscale normalization.
- Deterministic full-height plateau for a uniform-brightness foreground.
- Invert mode with `inverted = 1 - normal` inside the mask.
- Set/add/subtract markers.
- Circle, rectangle and polygon regions.
- Rim clipping count and warning.

Next:

- Optionally expose a user-selectable uniform-height value.
- Add smoothing/soften brush.
- Add region layers and local height locks.
- Add GUI editing and saved visual overlays.

## Task 5: Closed single-side solid

Status: indexed height-field implementation and generated fixture tests present; full CI evidence pending.

Implemented fixtures:

- Single cell.
- Rectangle and varying rectangular height field.
- Ring with a hole.
- Two unequal adjacent cells.
- 2×2 varying heights.
- Multiple fragments.
- Border-touching foreground.
- Empty mask export blocking.
- Preview/standard/high physical-size consistency.

Still required:

- Dedicated circle-like fixture.
- Full Windows suite result.
- Stable external image/mesh fixture artifacts where useful.

Next geometry work:

- Self-intersection detection.
- Component-level automatic orientation repair.
- True sharp constrained height steps.
- True bevelled and rounded rims.

## Task 6: Export and report

Status: OBJ, ASCII STL and GLB implemented.

Implemented:

- Shared finite `N×3` mesh validation.
- Integer and in-range face indices.
- Mirrored face winding correction.
- Atomic file replacement and parent creation.
- Unique project output names.
- Component-level closure and signed-volume report.
- Explicit `blocked` versus `review_required` manufacturing gate.
- STL millimeter convention recorded in build reports.

Next:

- Blender round-trip fixtures and recorded manual checks.
- Mesh read-back tests where practical.
- Local wall-thickness and minimum-feature analysis.
- Self-intersection report.
- Block zero-volume closed components explicitly.

## Task 7: Desktop GUI single-side workflow

Status: partial.

Implemented:

- New/open/save project.
- Front/back/reference import.
- Persisted width, height, base, relief, mask, invert, quality and rim controls.
- Controls are applied to the requested front/back build side and the active side is retained for later save.
- Worker-thread builds with duplicate-build prevention and worker cleanup.
- OBJ/STL/GLB actions.
- Readable error dialog/log output.
- Open output folder.

Required before completion:

- Original image preview.
- Exact mask overlay preview.
- Heightmap preview.
- Manual crop and mask editing.
- Explicit front/back parameter-side selector.
- Full report/warning panel.
- Unsaved-change prompt.
- GUI automated smoke tests on Windows.

## Task 8: Double-side production mode

Status: not implemented. Current output is inspection-only.

Current placeholder:

- Builds two complete single-side solids.
- Mirrors the back mesh and reverses winding.
- Exports named front/back objects for OBJ and GLB.
- Is explicitly marked non-fused and manufacturing-blocked.

Production requirements:

- Alignment controls for center, scale, rotation and X/Y offsets.
- One shared central body.
- No overlapping internal shells or gaps.
- One closed oriented final component.
- Unambiguous total-thickness semantics.

Do not mark this task complete until those requirements pass.

## Task 9: Windows delivery

Status: not implemented.

The old misleading `build_windows.bat` placeholder was removed. `run_windows.bat` is a development GUI launcher only.

Next:

- Choose PyInstaller or Nuitka.
- Build a versioned Windows executable.
- Test on a clean Windows machine without a development environment.
- Preserve CLI diagnostics.
- Include known limitations and manufacturing disclaimer.
