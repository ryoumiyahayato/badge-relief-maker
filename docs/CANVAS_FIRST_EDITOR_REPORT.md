# Canvas-first editor round 3 report

## Scope and revisions

- Repository: `ryoumiyahayato/badge-relief-maker`
- Pull request: Draft #8
- Base branch: `main`
- Fixed starting head: `d79665d860c4a5a595e3eec91ebb87de2173a48f`
- Code and test implementation head: recorded after the round-3 commit.
- Final branch head: recorded in the PR update after the documentation commit.

This round makes right-button drag the only canvas pan gesture, makes Shift +
wheel the only visible brush-size control, separates region/height/model tools,
restores functional grayscale editing and export, and hardens Windows text and
status rendering. The PR remains Draft.

## Implementation

### Pan and zoom

`CanvasEditor` exposes `_begin_pan(viewport_position)`, `_update_pan`, and
`_end_pan`; the only entry is explicit right-button drag. `NoDrag` and
`NoContextMenu` are set on the view, every right-button event is accepted, and
the path never creates a stroke or undo record. Pan cancels on focus loss,
Escape, tool/mode changes, and right-button release. Middle drag, Space + left
drag, and the old `移动` tool are removed.

The displayed zoom percentage is derived from the actual QGraphicsView
transform after `fitInView`, reset, or scale. Wheel zoom preserves the scene
point below the cursor where scrolling permits it. `Ctrl+0` fits the image and
`Ctrl+1` sets the actual transform to 100%.

### Brush model

The user-facing brush unit is integer screen pixels, range 2--300 px, default
24 px. Only Shift + mouse wheel changes it; ordinary wheel remains zoom. Region
and height modes persist separate last-used values, and the top status label is
read-only.

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
`生成模型`, `生成高度图`, `导出灰度图`, `添加区域`, `擦除区域`, `填充区域`,
`取背景色`, `去除背景`, `去背景强度`, and `模型精度`. Height normalization
and line parameters are inside a collapsed `高级调整` group. The tool rail is
filtered by the active stage and confirmation state. The current tool, brush
size, and zoom remain visible; detailed technical logs are collapsed behind
`详细信息`.

## Validation

- Baseline before this round: 276 tests passed at the fixed starting head.
- Current automated suite: 284 passed locally after the round-3 changes.
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

The user-provided complex badge image and screenshot/recording were not
available in this workspace. Automated Qt tests cover right-button pan,
rejected legacy gestures, scene-coordinate zoom, Shift + wheel brush scale,
cursor-to-stroke radius, stage gating, region selections, grayscale rendering,
export round trips, persistence, status deduplication and default wording. The
remaining manual pass must be performed on the user's Windows host with the
complex badge at 100%, 200%, 400% and 800%, including fine-line erase/recover,
DPI screenshots and interactive OBJ/STL/GLB export checks.

## Remaining items

- Capture the requested before/after Windows screenshots or short recording.
- Confirm the visual quality of white-background cleanup, bottom lettering,
  star tips, and positive/negative edge correction on the supplied badge.
- After the next manual pass, decide whether Draft PR #8 is ready for review;
  it should remain Draft for now.
