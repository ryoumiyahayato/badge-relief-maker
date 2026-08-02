# Canvas-first editor workflow

The default deterministic window is now a direct editor built around one large
canvas. The workflow is:

1. Open an image. The original source remains unchanged; an editor copy is
   resized to a maximum long edge of 1536 pixels.
2. In **区域**, choose `保留整张图`, `去除背景`, or `手动编辑`. Automatic
   background removal is an editable first draft: `去背景强度` is 0--100 and
   `边缘修正` is -20--20 px. Use `取背景色` for a sampled background and
   `重新计算` after changing a parameter.
3. Edit and confirm the region. The left rail provides `移动`, `添加区域`,
   `擦除区域`, `填充区域`, rectangle, and polygon tools. A drag is one
   normalized `stroke` record and one undo step.
4. In **高度**, choose the gray interpretation and edit the approved region.
   The brush slider and integer box use screen pixels (2--300 px, default
   24 px). The brush keeps its screen diameter while zooming, so at 800% the
   image-space radius is approximately one eighth of the 100% radius.
5. In **模型**, set physical parameters, choose `快速`/`标准`/`精细`, and
   generate OBJ, STL, or GLB in the background.

## Pan and zoom

All three pan entries use the same scene-coordinate implementation:

- middle-button drag;
- hold Space and drag with the left button;
- choose `移动` and drag with the left button.

`_begin_pan`, `_update_pan`, and `_end_pan` track the previous viewport point,
convert both points with the view transform, and move the scene center by the
scene-coordinate delta. Pan never creates a stroke or undo record and is
cancelled on tool/mode changes, focus loss, Escape, and key release.

The displayed zoom percentage comes from the actual QGraphicsView transform.
The wheel zoom keeps the scene point under the cursor when that point can be
scrolled into view. `Ctrl+0` fits the image and `Ctrl+1` returns to 100%.

## Persisted editor state

`project.json` uses `editor_schema_version: 2` and retains the existing
deterministic artifact names. New stroke records use normalized image
coordinates and are replayed against the original-resolution source when an
approval is saved:

```json
{
  "operation": "add",
  "shape": "stroke",
  "points": [[0.412, 0.275], [0.416, 0.278]],
  "coordinate_space": "normalized",
  "radius_normalized": 0.000009765625
}
```

The normalized radius above represents a 24 px screen brush at 800% on a
1536 px minimum dimension. It is calculated when the stroke starts and stays
fixed until release.

The loader continues to accept old circle, rectangle and polygon records. The
formal mesh path reads only the saved approved `solid_mask.png` and
`height_master_16bit.png`; the source image is never used to infer geometry
after approval.

## Responsiveness and background refinement

Draft generation and mesh construction run through `JobController` on the
Qt thread pool. Each job carries a request ID and cancellation token. A result
is applied only if its ID is still current for that job type. Parameter changes
are gated by a 200 ms single-shot debounce. Background strength and edge
refinement are applied to the preview in the worker, with only the latest
request accepted. The same normalized edge correction and ordered manual
stroke history are replayed against the original-resolution source on
confirmation. The bottom task bar reports progress, cancellation and full
error text while zoom, pan and window movement remain available.

The default UI shows `区域`, `高度`, `模型`, `确认区域`, `确认高度`,
`生成模型`, `去除背景`, `去背景强度`, `画笔大小`, and `模型精度`; advanced
height normalization controls start collapsed. Internal artifact names such as
`solid_mask` and `height_master` remain in project files and logs only.

For local acceptance, record import, preview, stroke p95, formal replay, mesh
build and peak-memory measurements in the development report. The automated
tests enforce pan entry consistency, scene-coordinate zoom, screen brush
sizing, stale-job handling, debounce, edge direction, persistence, and label
contracts; machine-specific timing remains an acceptance measurement.
