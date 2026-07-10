# Codex Tasks

`docs/BASELINE_V1.md` is the acceptance source of truth. Preserve the deterministic local relief pipeline; do not replace unresolved coordinate, topology or engineering work with optional AI.

## Working rule

1. Audit affected code for obvious regressions before adding features.
2. Fix blockers and semantic contradictions first.
3. Add tests for every core behavior change.
4. Do not mark implementation as accepted without current-commit evidence.
5. Keep all processing local and offline.
6. Keep the non-fused placeholder explicitly blocked.
7. Never describe advisory analysis as manufacturing certification.

## Task 0: Current Windows quality gate

Status: **highest priority; evidence pending**.

Run on the current head:

```powershell
python -m pip install -e ".[dev]"
python -m badge_relief_maker.app
python -m badge_relief_maker.app --help
python -c "from badge_relief_maker.app.ui.editor_window import MainWindow; print(MainWindow.__name__)"
python -m ruff check badge_relief_maker tests
python -m pytest -q
```

Required:

- Windows Python 3.10 and 3.12 pass.
- Record exact test count and commit in `docs/VALIDATION_RECORD.md`.
- Inspect any failure as a real regression until proven otherwise.
- Do not rely on the earlier intermediate 168-test run for the current commit.

## Task 1: Package artifact and clean-machine run

Status: build configuration implemented; evidence pending.

Required:

1. Let the Windows package workflow build `BadgeReliefMaker.exe`.
2. Download and launch it on a machine without the source checkout or Python environment.
3. Verify `--help`, GUI launch, project create/open/save and one sample export.
4. Record Windows version, artifact commit, file hash and result.
5. Add version metadata/icon only after the functional artifact passes.

## Task 2: Cross-quality visual-coordinate fixture

Status: core transforms and unit tests implemented; end-to-end fixture pending.

Required fixture:

1. Use one source with a non-trivial perspective transform, manual crop and automatic crop.
2. Add a source-space mask edit.
3. Add one final-mask click and one final-height/layer click.
4. Build preview, standard and high.
5. Verify the affected physical region differs by no more than one final grid cell.
6. Verify all X/Y dimensions remain within ±0.05 mm.
7. Save/reopen the project and repeat.

Also test that changing perspective prompts for clearing dependent edits and that clearing one side converts a `both` marker to the other side rather than deleting it globally.

## Task 3: GUI Windows interaction acceptance

Status: implementation candidate present; manual record pending.

Verify:

- source preview switches between oriented source for perspective and post-perspective source for crop/editing;
- mask and height previews represent the exact final grid;
- crop, mask, layer, set/add/subtract/smooth tools persist correctly;
- front/back parameter switching does not overwrite the wrong side;
- all mutable controls are disabled during a worker build;
- errors are readable and the report panel is complete;
- unsaved changes prompt on new/open/close;
- output folder action opens the actual export directory.

Add focused GUI tests where deterministic; keep screenshot/manual evidence in the validation record.

## Task 4: Project v2 robustness

Status: migration and schema implemented; adversarial coverage should continue.

Required:

- corrupt JSON and unsupported-version GUI recovery tests;
- malformed crop, perspective, mask edit, region layer and alignment records;
- negative, NaN, Infinity and wrong-type fields;
- asset symlink/junction containment behavior on Windows;
- v1 load → v2 save → equivalent rebuild test;
- repeated same-name imports and exports.

Fused validation rule:

- `total_thickness_mm` is central body thickness and is independent of `base_thickness_mm`;
- the two-base minimum applies only to the non-fused placeholder;
- front/back process profiles must be reconciled explicitly before one fused report is produced.

## Task 5: Single-side geometry acceptance

Status: implementation candidate present; current full suite and visual evidence pending.

Keep direct topology assertions for:

- single cell;
- rectangle;
- circle-like footprint;
- ring/hole;
- adjacent unequal heights;
- 2×2 varying heights;
- disconnected fragments;
- border contact;
- empty mask;
- exact layered plateaus;
- straight, sloped, bevel and rounded edges.

Every successful fixture must have zero open/non-manifold/inconsistent-winding edges, valid indices, zero zero-area faces, outward components and correct dimensions.

## Task 6: Manufacturing analysis hardening

Status: advisory implementation present.

Current implementation includes topology, orientation repair, bounded self-intersection broad phase, vertical-thickness, feature-size, tiny-component and orientation-based process checks.

Next:

- quantify and test the self-intersection candidate-limit behavior;
- add representative false-positive/false-negative fixtures;
- extend local thickness beyond vertical height-field estimates where practical;
- distinguish isolated decorative components from intended multi-part output;
- add more explicit mould draft and CNC tool-access summaries;
- keep `review_required` for every non-blocked result.

## Task 7: Fused double-side acceptance

Status: implementation candidate present; external alignment validation pending.

Required:

- asymmetric front/back fixtures that reveal horizontal flip errors;
- scale, rotation and positive/negative X/Y offset tests;
- union, intersection, front and back footprint tests;
- one shared body and exactly one final component;
- no internal overlapping shells or gaps;
- correct body-plus-relief Z dimensions;
- correct viewed-front/viewed-back orientation in Blender;
- matching or explicitly resolved process profiles.

Do not confuse this with the two-object inspection placeholder.

## Task 8: Export and external import evidence

Status: programmatic reload implemented; manual evidence pending.

For OBJ, STL and GLB:

- use the same accepted single-side fixture;
- verify dimensions, normals, object count, edit mode and non-manifold selection in Blender;
- verify STL millimeter interpretation;
- verify fused output as one object/component;
- retain representative sample exports and report JSON where repository size permits.

Then record slicer and CAM results separately. Programmatic trimesh reload is not a substitute.

## Task 9: Physical validation

Status: external and pending.

Produce at least one representative sample and record:

- process, machine and material;
- nominal and measured X/Y/Z;
- minimum surviving line width and relief depth;
- edge-profile quality;
- shrinkage, warping and unsupported-detail failures;
- adjustments required in Blender/slicer/CAM.

Only after this evidence may process-specific tolerance guidance be written.

## Task 10: Optional assistance

Optional AI segmentation/depth suggestions may be considered only after Tasks 0–9 establish stable deterministic behavior. AI output must remain editable, non-authoritative and local where practical.
