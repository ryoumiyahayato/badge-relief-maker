# Requirements, implementation and evidence traceability

A feature is not `passed` merely because code exists. External tools and physical processes remain `pending` until the exact commit, environment, fixture hash, run URL and artifact ID are recorded.

| ID | Implementation | Automated evidence | External evidence | Status |
|---|---|---|---|---|
| BRM-GITHUB-007 | PR branch and packaging files | PR CI | merged-commit run | implemented |
| BRM-CI-008 | `.github/workflows/tests.yml` | Windows 3.10/3.12 JUnit, Ruff, EXE hash/logs | required checks admin setting | implemented |
| BRM-CLEAN-009 | `clean-windows-smoke.yml`, standalone validator | packaged EXE flow | workflow artifact | implemented |
| BRM-GUI-010 | `tests/gui/test_full_editor_workflow.py` | real QTest mouse interaction | Windows DPI screenshot matrix | review_required |
| BRM-PROJECT-011 | JSON Schema and guarded loader | adversarial/migration tests | Windows UNC/junction matrix | implemented |
| BRM-GEOMETRY-012 | parameterized profiles and topology checks | geometry tests | Blender renders | implemented |
| BRM-MFG-013 | truncation, normal-ray thickness, multi-part, mould/CNC configuration | manufacturing tests | slicer/CAM/physical | implemented |
| BRM-FUSED-014 | asymmetric alignment matrix | fused matrix tests | Blender front/back evidence | implemented |
| BRM-BLENDER-015 | validator + pinned runner workflow | script syntax/unit tests | Blender artifact | pending |
| BRM-SLICER-016 | pinned-profile workflow | wrapper tests | slicer artifact | pending |
| BRM-CAM-017 | two-tool FreeCAD workflow | report schema tests | CAM artifact | pending |
| BRM-PHYSICAL-018 | schema, issue template, CI validator | schema tests | two measured physical samples | blocked |
| BRM-VERSION-019 | `pyproject.toml` + `version.py` + generated PE metadata | version consistency test | prerelease policy | implemented |
