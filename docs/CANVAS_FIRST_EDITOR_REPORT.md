# Canvas-first editor round 2 report

## Scope and revisions

- Repository: `ryoumiyahayato/badge-relief-maker`
- Pull request: Draft #8
- Base branch: `main`
- Fixed starting head: `58f1a4d8308a3149c5e139185ef2b6df96f2877f`
- Code and test implementation head: `1d4ab5beb5ef9af0069a941ae2c052f8851c016c`.
- Final branch head: recorded in the PR update after the documentation commit.

This round addresses stable pan/zoom, screen-space brush sizing, zoom-aware
normalized replay, direct editor wording, and practical background-edge
refinement. The PR remains Draft.

## Implementation

### Pan and zoom

`CanvasEditor` now exposes `_begin_pan(viewport_position)`, `_update_pan`, and
`_end_pan`. Middle drag, Space + left drag, and the `移动` tool all use that
same path. Each update maps the previous and current viewport points into scene
coordinates and moves the view center by their difference. Pan cancels on
focus loss, Escape, tool/mode changes, Space release, and mouse release; it
does not create a stroke or undo record.

The displayed zoom percentage is derived from the actual QGraphicsView
transform after `fitInView`, reset, or scale. Wheel zoom preserves the scene
point below the cursor where scrolling permits it. `Ctrl+0` fits the image and
`Ctrl+1` sets the actual transform to 100%.

### Brush model

The user-facing brush unit is integer screen pixels, range 2--300 px, default
24 px. Slider, spin box, `[`, `]`, and Shift + wheel share the same value;
entity/region and height modes persist separate last-used values.

At stroke start:

```text
view_scale = actual QGraphicsView scene scale
image_radius_px = screen_radius_px / view_scale
radius_normalized = image_radius_px / min(image_height, image_width)
```

The normalized radius is captured once per drag, persisted in the stroke
record, and replayed at original resolution. The cursor and stroke preview use
the same scene-space diameter, so a 24 px screen brush covers approximately
one eighth of the image radius at 800% compared with 100%.

### Background and edge refinement

- `背景类型`: `自动` / `浅色` / `深色`
- `去背景强度`: integer 0--100, mapped linearly to the internal RGB distance
  range 0--√3
- `边缘修正`: integer -20--20 px; negative values contract the mask and
  positive values expand it
- `取背景色` and `重新计算` remain available in the region page

Preview recalculation is debounced by 200 ms and runs through the existing
stale-result-safe job controller. Manual stroke history is applied after the
automatic/edge-refined draft. Formal confirmation repeats the same operation
against the original image dimensions, so a late preview result cannot replace
newer manual edits.

### Default wording and layout

The primary labels now use `区域`, `高度`, `模型`, `确认区域`, `确认高度`,
`生成模型`, `添加区域`, `擦除区域`, `填充区域`, `取背景色`, `去除背景`,
`去背景强度`, `画笔大小`, and `模型精度`. Height normalization and line
parameters are inside a collapsed `高级调整` group. Only the confirmation or
generation action for the current mode is visible in the top bar. The current
tool, brush size, and zoom remain visible.

## Validation

- Baseline before this round: 276 tests passed at the fixed starting head.
- Current automated suite: 282 passed.
- Ruff: passed with `python -m ruff check badge_relief_maker tests tools`.
- CLI `--help`: passed.
- CLI `--version`: passed (`Badge Relief Maker 0.3.0`).
- Windows packaging: `build_windows.ps1` passed on Windows 11 / Python
  3.12.13. `dist\BadgeReliefMaker.exe --help`, `--version`, and the approved
  artifact OBJ smoke path passed.
- Offscreen fixture check: `acceptance_fixtures/asymmetric_front.png` loaded,
  automatic region draft, -2 px edge refinement, and a subsequent manual erase
  completed without an exception.

## Manual Windows acceptance

The user-provided complex badge image and a screenshot/recording were not
available in this workspace. Automated Qt tests cover the three pan entries,
scene-coordinate zoom, brush scale, cursor-to-stroke radius, edge direction,
stale jobs, persistence, and default wording. The remaining manual pass must
be performed on the user's Windows host with the complex badge at 100%, 200%,
400%, and 800%, including fine-line erase/recover and interactive OBJ/STL/GLB
export checks.

## Remaining items

- Capture the requested before/after Windows screenshots or short recording.
- Confirm the visual quality of white-background cleanup, bottom lettering,
  star tips, and positive/negative edge correction on the supplied badge.
- After the next manual pass, decide whether Draft PR #8 is ready for review;
  it should remain Draft for now.
