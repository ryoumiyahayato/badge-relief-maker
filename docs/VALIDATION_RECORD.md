# Validation Record

This file records acceptance evidence that cannot be inferred from the presence of code. Do not mark a current status as passed without the tested commit, environment, fixture and observed result.

## PR #5 boundary-aware V10 review

Tested implementation commit: `45262ba648b4f409b3bacba3adfc15826b32545a`
Documentation follow-up commit: `a02926b4200bc4089da0eca57d7aebe8a3549bed`

### User-confirmed French emblem line-art fixture

The fixture uses the user-provided French emblem line drawing. The core library contains no France-, RF-, axe-, ribbon-, oak-, laurel- or leaf-specific rules. The following region assignments are project-level review annotations supplied or confirmed during the visual review:

- true void/background display regions: `7, 8, 11, 12, 17, 26, 38`;
- carrier surfaces: `1, 4, 6, 15, 19`;
- recessed/shadow region: `23`;
- foreground component regions: `10, 35`;
- lower-left oak branch and lower-right laurel branch receive separate rounded component layers;
- the RF outer surround uses a raised annular layer while the carrier and letter interiors stay below that surround;
- the upper fasces/axe and ribbons use separate rounded component mass.

Observed generated model:

- requested X/Y size: 100 × 150 mm;
- base thickness: 2.5 mm;
- configured front relief budget: 8.0 mm;
- observed maximum front relief: approximately 7.527 mm;
- observed total Z bounding-box thickness: approximately 10.027 mm;
- vertices: 210,240;
- triangles: 420,484;
- boundary edges: 0;
- non-manifold edges: 0;
- inconsistent winding edges: 0;
- closed oriented manifold: yes;
- OBJ groups: `front_relief`, `side_wall`, `flat_back`.

The front render, oblique surface and millimetre cross-sections were generated from the same final floating-point height field used to construct the OBJ. The oblique review view documented a 1.35× Z display exaggeration; the OBJ coordinates remained in true millimetres.

### Automated Windows validation

For documentation commit `a02926b4200bc4089da0eca57d7aebe8a3549bed`, the Windows Python 3.12 quality gate completed successfully, including package install, entry points, GUI import, Ruff and the complete pytest suite. The Python 3.10 gate completed the same checks successfully. The packaging smoke job was still running when this record was written and must be checked before presenting a new packaged EXE as verified.

### Remaining external validation

Not completed:

- Blender manual editability and visual inspection record;
- slicer import and printability review;
- CAM/tool-access review;
- mould/draft review;
- physical print or machined sample measurement;
- validation across multiple unrelated medal, badge and award artwork classes.

The V10 fixture demonstrates the corrected region-role workflow and closed editable mesh structure. It does not prove fully automatic semantic depth recovery from arbitrary line art.
