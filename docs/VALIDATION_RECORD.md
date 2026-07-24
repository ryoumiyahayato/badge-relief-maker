# Validation Record

This file records acceptance evidence that cannot be inferred from the presence of code. Do not mark a current status as passed without the tested commit, environment, fixture and observed result.

## PR #5 boundary-aware line-art correction

The earlier black-and-white `relief_preview.png` and the subsequent enclosed-region dome preview were rejected as acceptance evidence. They did not establish valid foreground/background boundaries or component depth ordering. The enclosed-region rule incorrectly turned letter interiors, shadows, holes and background gaps into raised solids and has been removed.

The current line-art workflow is conservative:

- the automatic field provides broad silhouette form and shallow engraved ink detail;
- a closed white region remains neutral and is never raised merely because it is enclosed;
- major regions separated by ink are reported as unresolved;
- the GUI can assign the selected region as `background`, `surface`, `raise` or `recess`;
- `background` removes the whole region from the physical footprint;
- region roles persist in the project;
- height smoothing excludes background and true-void pixels;
- feathered generic region layers establish broader carrier ordering without hard-coded object names.

Using the supplied French emblem line drawing, a boundary-confirmed demonstration generated:

- requested size: 100 × 150 mm;
- automatic flat back: 2.5 mm;
- configured outward relief budget: 4.0 mm;
- vertices: 216,160;
- triangles: 430,788;
- one shared editable OBJ with `front_relief`, `side_wall` and `flat_back` groups;
- boundary edges: 0;
- non-manifold edges: 0;
- inconsistent-winding edges: 0;
- closed oriented manifold: yes.

The review board is generated from the same final floating-point height field used by the editable OBJ. It includes a shaded front view, an oblique view of the actual mesh, a real-millimetre centre cross-section and a region-role map. The oblique display expands the visible Z scale for inspection but does not alter the exported OBJ coordinates.

Observed role corrections in this demonstration:

- RF/interior white regions remain near the central carrier surface rather than becoming the highest layer;
- the wreath is in front of the central panel;
- the flags and lower branches are behind the central assembly;
- the large white gap under the wreath is removed from the solid as a true void;
- the small region below the upper axe/fasces is recessed as shadow rather than raised.

These settings use generic region and polygon tools; the core algorithm contains no France, RF, wreath, flag, axe, animal or leaf-specific rules. The required confirmations are example-specific because one line drawing cannot unambiguously encode all occlusion and depth roles.

## Automated Windows quality gate

Commit `487c0e41b5824a2111fe838abd93d81b676c7235` passed the complete GitHub Actions quality gate:

- Windows Python 3.10 installation, entry points, GUI import, Ruff and full pytest: passed;
- Windows Python 3.12 installation, entry points, GUI import, Ruff and full pytest: passed;
- Windows PyInstaller executable build: passed;
- packaged executable `--help` smoke test: passed;
- executable artifact upload: passed.

A later documentation-only commit may produce a separate run; code acceptance evidence above identifies the exact tested commit.

## Programmatic validation assets

Programmatic mesh checks cover requested dimensions, closed topology, consistent winding, positive volume, OBJ/STL/GLB read-back and fused double-side output. These checks are necessary but do not establish sculptural quality or manufacturing fitness.

## GUI interaction validation

Status: automated coordinate coverage exists; a mouse-driven Windows interaction record is still pending.

Required flow:

1. Create and save a project.
2. Import a transparent PNG and an opaque controlled-background image.
3. Confirm the source, exact final mask and studio relief previews.
4. For a line drawing, inspect the numbered region map and unresolved count.
5. Apply `region background`, `region surface`, `region raise` and `region recess` on final previews.
6. Confirm that background regions become true voids and that smoothing does not bridge them.
7. Confirm explicit region roles persist after save/reopen.
8. Select a perspective quadrilateral and confirm dependent edits are reset rather than drifting.
9. Draw a crop on the post-perspective source.
10. Apply final-grid height and locked-layer brushes.
11. Change preview/standard/high and confirm the edit remains on the same physical region within one final cell.
12. Start a build and confirm mutable controls remain disabled until completion.

Record the commit, Windows scaling, display resolution, source fixture, exact clicks and screenshots.

## External application validation

Status: not yet recorded.

Use the same accepted single-side fixture for OBJ, STL and GLB. For OBJ, verify that `front_relief`, `side_wall` and `flat_back` are selectable groups within one closed object. Record dimensions, outward normals, non-manifold selection and side-view relief depth.

STL must be interpreted as millimeters because STL does not contain a unit declaration.

## Manufacturing validation

Status: not yet recorded.

Required evidence includes representative slicer import, CNC/CAM reachability, mould draft review where applicable, a physical sample and measured dimensions/tolerances. Automated topology checks are not a substitute for these records.
