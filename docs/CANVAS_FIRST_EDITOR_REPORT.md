# Canvas-first editor phase 1 report

## Baseline and final environment

- Base branch: `main`
- Base SHA: `fdb4a79a57feb6411f7dca96e0a9eea068d534b5`
- Development interpreter: Python 3.10.20 (`.venv310`)
- Packaging interpreter: Python 3.12.13 (`.venv`)
- Baseline before the change: Ruff passed; 266 tests passed; CLI help/version
  passed; offscreen GUI smoke started and exited cleanly.
- Final: Ruff passed; 276 tests passed; CLI help/version passed; offscreen GUI
  smoke passed.

The layout screenshot captured at 1366×768 is
[`canvas-first-editor-1366x768.png`](screenshots/canvas-first-editor-1366x768.png).
It shows the top operation bar, narrow tool rail, single central canvas, right
property stack and bottom task/log area. Native Windows font rendering should
be used for the Chinese labels during manual acceptance.

## Implemented structure

- `app/ui/deterministic_studio.py`: window assembly, project I/O, mode and
  approval coordination, formal replay and mesh coordination.
- `app/ui/canvas_editor.py`: one `QGraphicsView`/`QGraphicsScene`, normalized
  coordinate mapping, zoom/pan, layer compositing, stroke sampling and cursor.
- `app/ui/editor_controls.py`: operation bar, tool rail, three mode property
  pages, approval badges, layer visibility and opacity control.
- `app/ui/editor_session.py`: explicit mode/tool state, per-mode undo/redo and
  approval transitions.
- `app/ui/background_jobs.py`: `JobController`, `JobRequest`, `JobResult`,
  `JobError`, cancellation tokens, stale-result rejection and 200 ms debounce.
- `app/core/canvas_edits.py`: deterministic interpolation, stroke rasterization,
  ROI calculation and normalized replay helpers.

The deterministic core now accepts `stroke` records in addition to legacy
circle, rectangle and polygon records. `project.json` writes
`editor_schema_version: 2` and the existing formal artifact names remain
unchanged.

## Acceptance and performance data

The real metal badge fixture completed image import, preview editing, entity
approval, height editing, height approval and project write in the local
offscreen flow. The fixture is 353×384 pixels, so its preview copy remains the
same size. A temporary fixture project was removed after the run.

For a synthetic 1536×2048 image, the deterministic core measured:

| Operation | Seconds |
| --- | ---: |
| Source import | 0.355 |
| Solid draft | 0.017 |
| Height draft | 0.310 |
| Formal artifact write | 0.479 |
| Draft-quality mesh build | 50.081 |

Peak RSS was not available from the installed development environment. Stroke
and pan/zoom work is kept on the preview copy; formal replay and mesh building
are dispatched through the worker controller. Automated tests cover stale
request IDs, cancellation, debounce, coordinate invariance, continuous
strokes, undo/redo and project reopening.

## Known remaining items

- A second manual Windows pass with the user-provided complex badge should
  capture live screenshots/recording for fine-line cleanup and verify all OBJ,
  STL and GLB exports interactively.
- Timing and peak-memory thresholds are machine acceptance measurements rather
  than hard CI assertions.
- The current phase keeps compatibility aliases for the prior deterministic
  test/API names; they can be removed after downstream consumers migrate.
