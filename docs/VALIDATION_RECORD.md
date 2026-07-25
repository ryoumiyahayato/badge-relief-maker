# Validation Record

This file records acceptance evidence that cannot be inferred from the presence of code. Do not mark a current status as passed without the tested commit, environment, fixture and observed result.

## PR #5 grayscale-first V11 review

Current grayscale-first implementation commits:

- `1e66656346ab54d613f531589b2d4da161a331b8`: project/CLI/GUI grayscale-master export;
- `7b0e37c0ffe0f37bea83512336e0cdbec69d5ba8`: scalable 8K export and source-resolution linework reconstruction;
- `f32d9b4df847b1e0abde2644f5863907895a6808`: explicit approved-heightmap-to-mesh CLI path;
- `341860b374df959786574a95526de69862f39130`: correct 16-bit height normalization;
- `4813c4bc96b9b73252bb5704304fbd3ceaa43761`: cumulative correction and approved-master contract.

### Acceptance order

The editable grayscale master is now the acceptance artifact. A 3D preview or mesh is not accepted as a substitute. Mesh generation remains deferred until the grayscale PNG/TIFF is reviewed.

### User-confirmed French emblem fixture

The user clarified that corrections are cumulative. The confirmed void/background display regions are:

`5, 7, 8, 10, 11, 12, 17, 20, 26, 38`

The V11 review project preserves all ten entries as `background`; region 10 is no longer treated as a foreground component. The export manifest records the applied void list and states that later exports must not discard earlier confirmed voids.

Observed V11 master export:

- requested/final canvas: 5875 × 8192 pixels;
- editable height PNG: 16-bit unsigned grayscale;
- editable height TIFF: 32-bit floating point;
- separate aligned source, recovered linework, solid mask and void mask;
- broad component synthesis grid: 2938 × 4096;
- source linework reconstructed directly at the final 5875 × 8192 resolution;
- mesh generation: intentionally deferred.

The original fixture image is 408 × 612 pixels. Upscaling alone cannot create genuine new sculptural information; the V11 exporter therefore separates high-resolution contour recovery from broad component mass and exports both the height master and linework mask for manual editing.

### Approved-master conversion contract

The new conversion path accepts an explicitly approved 16-bit PNG or 32-bit TIFF plus an optional solid mask. It does not re-read the source artwork, perform line-art inference, add embossing or invent semantic height. The approved grayscale is the source of truth. A test verifies that 16-bit values survive normalization and produce the expected relief thickness.

### Automated Windows validation

Workflow run `30148329660` completed the Windows Python 3.10 and Python 3.12 quality gates successfully, including package installation, entry points, GUI import, Ruff and the complete pytest suite. Later approved-master commits are being revalidated by the current branch workflow and must pass before a new packaged executable is presented.

### Remaining work

- the current French emblem height master is an architecture and topology correction, not yet a professional final sculptural master;
- region-level height shaping and fine grayscale refinement still require further work;
- no new OBJ/STL/GLB should be presented as accepted until the grayscale master passes visual review;
- Blender, slicer, CAM, mould and physical-sample validation remain pending;
- multiple unrelated medal, badge and award classes still need validation.
