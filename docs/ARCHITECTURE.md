# Architecture

Badge Relief Maker is organized around one deterministic core that is consumed
by the CLI, project workflows and the desktop editor. The public layers may
select parameters and coordinate work; image, mesh and persistence rules remain
in `app/core`.

## Dependency direction

```text
CLI / desktop editor
        |
        v
project_build ---------> project_io
        |                     |
        v                     v
project_parameters      project_model
        |
        v
single_side_pipeline / double_side_builder
        |
        v
image + marker + mesh primitives
        |
        v
shared catalogs, validation, components, mesh data, units and atomic I/O
```

Lower layers do not import the CLI or UI. Persisted project dataclasses do not
act as runtime build parameters: `project_parameters` is the explicit validated
adapter between those two representations.

## Build flows

### Single side

```text
load and orient image
  -> optional perspective correction
  -> mask generation and source-space mask edits
  -> crop, cleanup and grid resize
  -> grayscale/layer/hybrid height field
  -> final-grid layer and height edits
  -> rim and edge profile
  -> indexed closed solid
  -> repair and advisory analysis
  -> atomic OBJ/STL/GLB export
```

`prepare_relief_field` owns the image-to-field transformation.
`build_single_side_relief` owns mesh construction, report composition and
optional export. Callers needing previews or double-sided assembly reuse the
prepared field rather than duplicating image processing.

### Project and double side

`project_build` owns project-level orchestration, derived paths, unique export
names and export-history updates. Its `ProjectBuildWorkspace` is the sole
abstraction for build output and preview locations.

The placeholder workflow deliberately emits two separate complete solids. The
fused workflow prepares both fields with the same quality mode, aligns them onto
one grid, constructs one shared body, repairs it and blocks export if mandatory
manufacturing checks fail.

## Shared contracts

The following modules are deliberately small single sources of truth:

- `options.py`: ordered values, defaults and aliases for CLI, UI, models and
  validation.
- `validation.py`: strict finite-number, integer and normalized-value checks.
- `project_parameters.py`: project validation and persisted-to-runtime mapping.
- `marker_schema.py`: marker types, operations, shapes, coordinate aliases and
  height keys.
- `components.py`: deterministic 4/8-connected binary-grid traversal and labels.
- `mesh_data.py`: strict `N x 3` vertex/face normalization, valid-face masks and
  signed volume.
- `atomic_io.py`: flush, `fsync` and atomic replacement for project and mesh
  files.
- `units.py`: report/export unit conventions.

Feature modules should import these contracts. They should not create local
copies of supported-value sets, marker aliases, breadth-first searches, mesh
array validators or temporary-file replacement logic.

## Persistence boundary

`project_model.py` defines tolerant JSON-facing dataclasses. Unknown saved
fields are ignored so older and forward-extended files can still be read.
`project_io.py` validates versions, constrains asset paths to the project asset
root and performs atomic saves.

Runtime code uses immutable `ReliefParameters`. New saved settings therefore
require three explicit changes:

1. Add the persisted field to the appropriate project dataclass.
2. Validate and map it in `project_parameters.py`.
3. Consume it in the relevant core stage and cover the path with a test.

Do not persist derived reports or fields that can be reproduced during a build.

## Desktop UI

The UI has one public entry point:

```python
from badge_relief_maker.app.ui.main_window import MainWindow
```

`ProjectWindow` provides project controls, asynchronous build plumbing and
explicit preview/edit hooks. `editor_window.MainWindow` implements
coordinate-safe source/final-grid editing and external export copies.
`ui/main_window.py` only exposes that concrete editor, preventing two divergent
window implementations.

## Extension rules

- Add a string option to `options.py` first, then derive model, CLI and UI
  choices from that catalog.
- Add marker vocabulary to `marker_schema.py`; keep transforms and application
  code schema-driven.
- Reuse `connected_components`, `mesh_data` and `atomic_writer`.
- Keep project-file load/build/save wrappers on `_run_project_file_build`.
- Preserve physical-dimension semantics: single-side base thickness and fused
  central-body thickness are different settings.
- Treat manufacturing reports as advisory; they never certify a model.

## Known complexity

Geometry construction, self-intersection analysis and manufacturing reporting
remain algorithmically dense. Their branch and argument counts are monitored as
maintainability debt, but are not split solely to satisfy a metric: any future
extraction must preserve topology, coordinate and manufacturing-report
invariants with focused tests.
