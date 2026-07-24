# Validation Record

This file records acceptance evidence that cannot be inferred from the presence of code. Do not mark a current status as passed without the tested commit, environment, fixture and observed result.

## PR #5 sculptural-relief correction

The earlier black-and-white `relief_preview.png` was rejected as acceptance evidence. It mainly exposed line edges and did not demonstrate the broad sculptural high/low form expected from a medal-like bas-relief.

The current branch now separates continuous-tone artwork from achromatic line artwork. Line drawings are no longer interpreted as one flat white maximum surface with black grooves. The line-art path combines:

- global silhouette doming;
- local doming of enclosed light regions;
- medium-scale mass inferred from broad ink density;
- shallow engraved line detail;
- a studio preview whose normals, cavity shading and highlights are calculated from the same final height field used for mesh export.

Using the supplied French emblem line drawing, the current local verification produced:

- artwork interpretation: `lineart`;
- requested size: 100 × 150 mm;
- flat-back thickness: 2.5 mm;
- outward relief range: 4.0 mm;
- connected mesh components: 1 after disconnected scan-dust cleanup;
- boundary edges: 0;
- non-manifold edges: 0;
- inconsistent-winding edges: 0;
- OBJ groups: `front_relief`, `side_wall`, `flat_back`.

This establishes that the implementation is now moving toward a sculptural 2.5D relief rather than an engraved plate. It does not establish semantic professional modelling. The algorithm does not yet understand that a contour represents a particular leaf, animal, flag or separate foreground layer, and it cannot infer hidden surfaces or undercuts from one image.

## Automated Windows quality gate

Current working-tree status: **final GitHub Actions run pending**.

The workflow is configured for Windows Python 3.10 and 3.12 and runs installation, CLI entry points, corrected GUI import, Ruff and full pytest. A dependent Windows 3.12 job builds, smoke-tests and uploads `BadgeReliefMaker.exe`.

## Programmatic validation assets

Programmatic mesh checks cover requested dimensions, closed topology, consistent winding, positive volume, OBJ/STL/GLB read-back and fused double-side output. These checks are necessary but do not establish sculptural quality or manufacturing fitness.

## GUI interaction validation

Status: automated coordinate coverage exists; a mouse-driven Windows interaction record is still pending.

Required flow:

1. Create and save a project.
2. Import a transparent PNG and an opaque controlled-background image.
3. Confirm the source, exact final mask and studio relief previews.
4. Confirm a line drawing shows broad high/low form rather than only shallow black-line grooves.
5. Select a perspective quadrilateral and confirm dependent edits are reset rather than drifting.
6. Draw a crop on the post-perspective source.
7. Add/remove mask regions from source and final-mask previews.
8. Apply final-grid height and locked-layer brushes.
9. Change preview/standard/high and confirm the edit remains on the same physical region within one final cell.
10. Start a build and confirm mutable controls remain disabled until completion.
11. Save, close, reopen and confirm all v2 settings and edits persist.

Record the commit, Windows scaling, display resolution, source fixture, exact clicks and screenshots.

## Blender import validation

Status: not yet recorded.

Use the same accepted single-side fixture for OBJ, STL and GLB. For OBJ, verify that `front_relief`, `side_wall` and `flat_back` are selectable groups within one closed object. Record dimensions, outward normals, non-manifold selection and side-view relief depth.

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
