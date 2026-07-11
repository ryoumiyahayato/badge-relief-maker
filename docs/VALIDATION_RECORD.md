# Validation Record

This file records acceptance evidence that cannot be inferred from the presence of code. Do not mark a current status as passed without the tested commit, environment, fixture and observed result.

## Automated Windows quality gate

Current working-tree status: **local Windows gates passed; GitHub Actions run still pending**.

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
| Base commit | `e15ebe79b4c1672f968ba316441390e603cb30f1` |
| Working tree under test | base commit plus coordinate/project/manufacturing/double-alignment/GUI regressions, fixes, Windows version metadata/build checks and documentation; not yet committed |
| Windows version | Windows NT 10.0.26100.0; Windows 10 IoT Enterprise LTSC 2024, build 26100 |
| Python 3.10 local quality gate | Python 3.10.20; CLI, `--help`, `--version`, corrected GUI import, Ruff and `226 passed` |
| Python 3.12 local quality gate | Python 3.12.13; CLI, `--help`, `--version`, corrected GUI import, Ruff and `226 passed` |
| GitHub Actions Python 3.10/3.12 jobs | pending; combined status and available commit workflow-run queries returned no records |
| Local package build | passed with PyInstaller 6.21.0 on Python 3.12.13 |
| Executable artifact | `dist/BadgeReliefMaker.exe`, 65,449,711 bytes, file/product/CLI version `0.3.0`, SHA-256 `AAE579BCC1A850B0DF7B628D5DD8E0FABBC759E2A5A08E722751B601B018B97B` |
| Packaged CLI smoke | `--help` and `--version` passed; direct single and project-based fused OBJ/STL/GLB builds all passed independent trimesh read-back |
| Packaged GUI smoke | no-argument offscreen launch remained alive for eight seconds; both PyInstaller parent/child test processes were stopped afterward |
| Clean machine launch | pending |

The local run is current-working-tree regression evidence, not a substitute for the
configured GitHub Actions matrix or a clean Windows machine. The executable was
built and launched on the development machine that contains Python and project
dependencies, although the executable itself was launched through its PyInstaller
bundle.

## Programmatic validation assets

Current working-tree status: **generated and independently reloaded; external applications pending**.

`python -m tools.generate_validation_assets <temp-directory> --max-grid-cells 5000`
generated the seven expected exports. Independent `trimesh 4.12.2` read-back
reported one geometry, matching dimensions, watertight topology, consistent
winding and positive volume for the single-circle and fused OBJ/STL/GLB files.
The ring OBJ also passed its programmatic export validation. The fused mesh report
recorded one closed, outward-oriented component with no boundary or non-manifold
edges.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `fused_asymmetric_80x60.glb` | 378,704 | `326ACF251D8C23314B73D5834F629BF560DC0E4DBE7F1BDB6993E50E01624CDE` |
| `fused_asymmetric_80x60.obj` | 507,341 | `B36455045CA9AC0C97ED6927215BD36B80896A7C1097F36ADA8FD4FA79A6CCB1` |
| `fused_asymmetric_80x60.stl` | 3,266,313 | `E8A4D905D93CB6D51C6BC69BCB8DF23E3C4DB0902C76C68DDFCC3D530C6B8023` |
| `single_circle_80x60.glb` | 374,672 | `06624A8EE67A9907F9EEAD2A2763BD0FB6F7307254AE657B2326D5460143A44B` |
| `single_circle_80x60.obj` | 501,871 | `199D009B3759509FE63CA292A0C00E721E49FDE76817D3368420D807D1B0A5CE` |
| `single_circle_80x60.stl` | 3,230,739 | `3E644C9244DC5B7D451FE4A059406E3D3878E59ADF3817269CBDDBA0D5BC5B4A` |
| `single_ring_80x60.obj` | 387,052 | `8C082160505C30A7EE72DE04D1F2CF820C6AC47D517D9D2090FF953F763A63D1` |

These hashes identify this local generation only. Dependency changes can alter
serialization without changing geometry, so future acceptance runs must record
their own hashes rather than treating these values as universal golden files.

The fused hashes changed after two alignment defects were fixed: Pillow's 16-bit affine path truncated normalized back heights, and its affine center convention shifted 180-degree rotation by one pixel. The final implementation uses float height fields and explicit pixel-center inverse mapping. The final validation manifest SHA-256 is `9833FD364408740885E6AEC601D3774A63A7C644AEA052BCA5E637017CB9C402`.

## GUI interaction validation

Status: automated coordinate coverage passed on the current working tree; a mouse-driven Windows interaction record is still pending.

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
