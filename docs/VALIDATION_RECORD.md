# Validation Record

This file records manual acceptance evidence that cannot yet be proven by the Python unit suite. Do not change a status to passed without recording the tested commit, environment, input fixture and observed result.

## Windows clean-environment validation

Status: not yet recorded.

| Field | Value |
|---|---|
| Commit | pending |
| Windows version | pending |
| Python version | pending |
| Clean virtual environment | pending |
| `pip install -e ".[dev]"` | pending |
| No-argument CLI | pending |
| `--help` | pending |
| GUI launch | pending |
| Ruff critical checks | pending |
| Full pytest | pending |

## Blender import validation

Status: not yet recorded.

For each format, use the same accepted single-side fixture and record:

| Check | OBJ | STL | GLB |
|---|---|---|---|
| Commit | pending | pending | pending |
| Blender version | pending | pending | pending |
| File opens | pending | pending | pending |
| Expected object count | pending | pending | pending |
| X dimension | pending | pending | pending |
| Y dimension | pending | pending | pending |
| Z dimension | pending | pending | pending |
| Outward normals | pending | pending | pending |
| Edit mode works | pending | pending | pending |
| Non-manifold selection result | pending | pending | pending |
| Notes | pending | pending | pending |

STL must be interpreted as millimeters during the import workflow because STL does not contain a unit declaration.

## Slicer validation

Status: not yet recorded.

Record slicer name/version, import scale, detected shells, non-manifold repairs, estimated dimensions and any automatic repair warnings.

## CAM validation

Status: not yet recorded.

Record CAM application/version, imported dimensions, detected open surfaces, tool-access concerns and any geometry conversion required before toolpath generation.

## Physical sample validation

Status: not yet recorded.

Record process, material, machine, nominal dimensions, measured dimensions, minimum surviving line width, minimum surviving relief depth, edge quality and observed failure modes.

## Release interpretation

- Automated topology success is necessary but does not replace this record.
- A blank or pending record means the corresponding manual acceptance has not happened.
- The double-side placeholder is excluded from production acceptance because it is not fused.
