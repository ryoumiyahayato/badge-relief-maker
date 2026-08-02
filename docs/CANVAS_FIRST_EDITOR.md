# Canvas-first editor workflow

The default deterministic window is now a direct editor built around one large
canvas. The workflow is:

1. Open an image. The original source remains unchanged; an editor copy is
   resized to a maximum long edge of 1536 pixels.
2. Edit and approve the solid mask. Add, erase, fill, rectangle and polygon
   tools are available from the left rail. A drag is one normalized `stroke`
   record and one undo step.
3. Edit and approve the height master in the same canvas. Set, raise, lower and
   smooth strokes are constrained to the approved solid mask.
4. Set physical mesh parameters, build in the background, and export OBJ, STL
   or GLB.

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
  "radius_normalized": 0.0125
}
```

The loader continues to accept old circle, rectangle and polygon records. The
formal mesh path reads only the saved approved `solid_mask.png` and
`height_master_16bit.png`; the source image is never used to infer geometry
after approval.

## Responsiveness

Draft generation and mesh construction run through `JobController` on the
Qt thread pool. Each job carries a request ID and cancellation token. A result
is applied only if its ID is still current for that job type. Parameter changes
are gated by a 200 ms single-shot debounce. The bottom task bar reports
progress, cancellation and full error text while zoom, pan and window movement
remain available.

For local acceptance, record import, preview, stroke p95, formal replay, mesh
build and peak-memory measurements in the development report. The automated
tests enforce the coordinate, stroke, stale-job, debounce and persistence
contracts; machine-specific timing remains an acceptance measurement.
