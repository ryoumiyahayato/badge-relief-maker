# 2026-07-11 Completion Audit

## Scope and authority

- GitHub repository: `ryoumiyahayato/badge-relief-maker`.
- Cloud default branch and local base were both `main` at `e15ebe79b4c1672f968ba316441390e603cb30f1` when this follow-up began.
- The local base working tree was clean before the follow-up changes were applied.
- The cloud repository contains a `tests` workflow with Windows Python 3.10/3.12 quality jobs and a dependent Python 3.12 PyInstaller artifact job. It does not contain a Release publishing workflow.
- No workflow was rerun/cancelled, no tag or Release was created, and nothing was pushed while cloud release state was being respected.
- This record covers the current uncommitted working tree based on that cloud commit. GitHub Actions evidence can only exist after the changes are committed and pushed.

## Completed implementation corrections

1. Fused back-height alignment now keeps normalized heights as 32-bit floats. The prior Pillow `I;16` affine path could reduce a full-height value to about `255/65535`, making the back relief nearly flat.
2. Fused flip/scale/rotation/offset now uses explicit pixel-center inverse mapping. This removes the one-row/one-column shift observed for a 180-degree rotation and gives deterministic positive/negative millimeter offsets.
3. Single-side validation no longer consumes `total_thickness_mm`, which belongs to fused/placeholder workflows. Fused and project-wide validation still require a positive finite value.
4. Project loading recursively rejects `NaN`, positive/negative infinity and overflowed JSON floats at any nesting depth.
5. Malformed v2 crop, perspective, mask-edit and region-layer records are filtered into safe values before GUI use.
6. Windows symlink/junction asset escapes are covered by a real reparse-point regression and remain blocked by resolved-path containment.
7. GUI height/layer tools accept only the final-grid previews. Source clicks after perspective can no longer be persisted under the wrong coordinate contract.
8. Source/mask/height previews are disabled during worker builds, and preview-edit handlers also reject edits while a worker is active.
9. Self-intersection reports now expose the configured candidate limit and whether it was reached; separated coplanar and crossing fixtures cover false-positive/positive behavior.
10. Manufacturing reports classify isolated foreground regions and give explicit +Z assumptions plus CNC/mould/FDM/resin limitations.
11. The Windows artifact exposes `Badge Relief Maker 0.3.0` through `--version` and Windows file/product metadata.
12. The build script now stops immediately when dependency installation or PyInstaller fails and reports a running EXE lock before attempting a rebuild.

## Automated evidence

### Python quality gates

Both environments passed the same current working tree:

| Environment | Result |
|---|---|
| Windows Python 3.10.20 | CLI, help, version, GUI import, Ruff, `226 passed` |
| Windows Python 3.12.13 | CLI, help, version, GUI import, Ruff, `226 passed` |

### Coordinate and project evidence

- Non-trivial perspective, manual crop and automatic crop execute in one saved/reopened project fixture.
- Source-space mask removal, final-grid locked layer and final-grid height edit persist after reopen.
- Preview/standard/high place the edit within one final cell of the same physical point.
- Requested X/Y dimensions stay within the v1 tolerance.
- v1 load → v2 save → rebuild produces equivalent vertices, faces and bounds.
- Corrupt JSON, future versions, non-finite values, wrong numeric types and malformed v2 visual records have deterministic behavior.

### Geometry and export evidence

- Single-cell, rectangle, circle, ring/hole, varying height, disconnected, border, empty, layered and all four edge-profile fixtures pass topology assertions.
- Fused tests cover viewed-back flip, scale, 180-degree rotation, positive/negative X/Y offset, union/intersection/front/back footprints, one shared component and body-plus-relief Z size.
- Source-generated single/fused OBJ/STL/GLB exports reload through trimesh as one watertight, winding-consistent, positive-volume geometry with matching dimensions.
- The final packaged EXE independently generated six accepted files:
  - single circle OBJ/STL/GLB: `40 × 40 × 3 mm`;
  - fused asymmetric OBJ/STL/GLB: `80 × 80 × 10 mm`.
- All six packaged outputs passed the same independent read-back properties.

### Windows artifact

| Field | Value |
|---|---|
| Path | `dist/BadgeReliefMaker.exe` |
| Bytes | `65,449,711` |
| SHA-256 | `AAE579BCC1A850B0DF7B628D5DD8E0FABBC759E2A5A08E722751B601B018B97B` |
| File/Product/CLI version | `0.3.0` |
| GUI smoke | Alive for 8 seconds in offscreen mode; test parent/child processes cleaned up |
| Signature | Not signed |

## Reproduction steps

From the repository root on Windows:

```powershell
python -m pip install -e ".[dev]"
python -m badge_relief_maker.app
python -m badge_relief_maker.app --help
python -m badge_relief_maker.app --version
python -c "from badge_relief_maker.app.ui.editor_window import MainWindow; print(MainWindow.__name__)"
python -m ruff check badge_relief_maker tests tools packaging_entry.py
python -m pytest -q
build_windows.bat
python -m tools.generate_acceptance_fixtures acceptance_fixtures
python -m tools.generate_validation_assets validation_assets/current --max-grid-cells 5000
```

Expected local result: `226 passed`, Ruff success, version `0.3.0`, a successfully smoke-tested `dist/BadgeReliefMaker.exe`, and seven validation exports plus `validation_manifest.json`.

## External acceptance that cannot be manufactured by code changes

The implementation and reproducible local digital gates are complete for the repository scope. The following are evidence-gathering tasks requiring other environments, licensed/installed applications or physical equipment:

1. GitHub Actions run for the committed follow-up.
2. Launch on a separate clean Windows machine without Python/source checkout.
3. Blender imports and screenshots for dimensions, object count, normals, edit mode, non-manifold selection and profiled-edge appearance.
4. Slicer shell/repair/support/feature results.
5. CAM open-surface, cutter-diameter and tool-access results.
6. A measured printed, machined or moulded sample.
7. Optional branding icon and production code signing certificate.

These items must remain `pending` until observed. Programmatic reload and advisory analysis must not be relabelled as Blender, slicer, CAM or physical validation.

## Release cautions

- Do not trigger, cancel or rerun a cloud package/Release job merely to refresh this record.
- Before publishing, commit the working tree, let the configured Actions matrix run on that exact commit, and download the artifact produced by that run.
- Compare artifact version and hash with the release notes; do not reuse the local hash as a universal golden value.
- Do not publish the unsigned local EXE as a trusted production binary without an explicit unsigned-artifact policy or code signing.
- Keep every manufacturing result at `review_required` unless a known blocker changes it to `blocked`; never advertise unattended manufacturing certification.
