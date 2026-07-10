# Validation Record

This file records acceptance evidence that cannot be inferred from the presence of code. Do not mark a current status as passed without the tested commit, environment, fixture and observed result.

## Automated Windows quality gate

Current-commit status: **pending**.

The latest workflow is configured for Windows Python 3.10 and 3.12 and runs installation, CLI entry points, corrected GUI import, Ruff and full pytest. A dependent Windows 3.12 job builds, smoke-tests and uploads `BadgeReliefMaker.exe`.

### Historical intermediate local run

The interrupted development session reported the following before the final GUI/coordinate continuation:

| Field | Recorded result |
|---|---|
| Environment | isolated Python 3.12 virtual environment |
| `pip install -e ".[dev]"` | passed |
| no-argument CLI | passed |
| `--help` | passed |
| GUI module import | passed |
| Ruff configured checks | passed |
| First pytest run | 167 passed, 1 failed due to a test treating a string path as `Path` |
| Regression after core/fused changes | reported as 168 passed |
| Current commit covered | no |

This is useful historical evidence, but it is not acceptance evidence for the current commit because visual-editor coordinate fixes, fused validation changes, additional tests and workflow changes were added afterward.

### Current run fields

| Field | Value |
|---|---|
| Commit | pending current head |
| Windows version | pending |
| Python 3.10 quality job | pending |
| Python 3.12 quality job | pending |
| Package build job | pending |
| Executable artifact | pending |
| Clean machine launch | pending |

## GUI interaction validation

Status: not yet recorded on the current commit.

Required flow:

1. Create and save a project.
2. Import a transparent PNG and an opaque controlled-background image.
3. Confirm the source, exact final mask and heightmap previews.
4. Select a perspective quadrilateral and confirm dependent edits are reset rather than drifting.
5. Draw a crop on the post-perspective source.
6. Add/remove mask regions from source and final-mask previews.
7. Apply final-grid height and locked-layer brushes.
8. Change preview/standard/high and confirm the edit remains on the same physical region within one final cell.
9. Start a build and confirm mutable controls remain disabled until completion.
10. Save, close, reopen and confirm all v2 settings and edits persist.

Record the commit, Windows scaling, display resolution, source fixture, exact clicks and screenshots.

## Blender import validation

Status: not yet recorded.

Use the same accepted single-side fixture for all formats and one aligned fused double-side fixture.

| Check | OBJ | STL | GLB | Fused double |
|---|---|---|---|---|
| Commit | pending | pending | pending | pending |
| Blender version | pending | pending | pending | pending |
| File opens | pending | pending | pending | pending |
| Expected object count | pending | pending | pending | pending |
| X dimension | pending | pending | pending | pending |
| Y dimension | pending | pending | pending | pending |
| Z dimension | pending | pending | pending | pending |
| Outward normals | pending | pending | pending | pending |
| Edit mode works | pending | pending | pending | pending |
| Non-manifold selection | pending | pending | pending | pending |
| Edge profile appearance | pending | pending | pending | pending |
| Notes | pending | pending | pending | pending |

STL must be interpreted as millimeters because STL does not contain a unit declaration.

## Slicer validation

Status: not yet recorded.

Record slicer name/version, import scale, shell count, automatic repair warnings, estimated dimensions, unsupported regions and whether small text/lines survive slicing.

## CAM validation

Status: not yet recorded.

Record CAM application/version, imported dimensions, open-surface detection, cutter/tool-access concerns, inaccessible relief valleys and any geometry conversion required before toolpath generation.

## Physical sample validation

Status: not yet recorded.

Record process, material, machine, nominal and measured dimensions, minimum surviving line width, minimum surviving relief depth, edge quality, warping/shrinkage and observed failure modes.

## Release interpretation

- Automated topology success is necessary but does not replace this record.
- A blank or pending field means the acceptance step has not happened.
- Programmatic trimesh reload is not a substitute for Blender, slicer or CAM import.
- The non-fused placeholder is excluded from production acceptance.
- The fused double-side path is still a candidate until alignment and external import evidence are recorded.
- No report produced by the application is a manufacturing certification.
