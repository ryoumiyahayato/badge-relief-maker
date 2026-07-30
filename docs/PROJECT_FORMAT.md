# `.medalproj` Project Format

A `.medalproj` file is UTF-8 JSON. It is untrusted project metadata, not executable content. Imported images, previews and exports live in the sibling `<project_stem>_assets/` directory.

## Versioning

The current supported `file_version` is `2`.

- Version 1 files are migrated in memory to version 2 defaults when loaded.
- Non-integer, zero or negative versions are rejected.
- Versions newer than the implementation are rejected with `UnsupportedProjectVersionError`.
- Unknown fields in a supported version are ignored.
- Saving writes the current supported version.

## Top-level structure

```json
{
  "name": "Example Medal",
  "file_version": 2,
  "created_at": "2026-07-10T00:00:00+00:00",
  "updated_at": "2026-07-10T00:00:00+00:00",
  "same_physical_object": true,
  "front_image": null,
  "back_image": null,
  "reference_images": [],
  "dimensions": {},
  "edge": {},
  "front_relief": {},
  "back_relief": {},
  "double_side": {},
  "manual_markers": [],
  "export_history": []
}
```

## Image record

```json
{
  "role": "front",
  "path": "example_assets/images/front_source.png",
  "original_path": "C:/source/front.png",
  "is_reference": false,
  "quality_label": "unknown",
  "notes": "",
  "preprocessing": {}
}
```

`path` is resolved relative to the project directory and must remain inside the sibling project asset root after `resolve()`. The original source path is informational only.

## Dimensions and thickness semantics

```json
{
  "width_mm": 80.0,
  "height_mm": 60.0,
  "total_thickness_mm": 4.0,
  "base_thickness_mm": 2.0
}
```

- `width_mm` and `height_mm` are the final foreground X/Y dimensions.
- `base_thickness_mm` is the flat backing used by one single-side model.
- `total_thickness_mm` is the shared central-body thickness used by fused double-side output; it excludes outward front and back relief.
- A single-side build uses `base_thickness_mm` and does not consume or constrain `total_thickness_mm`.
- The non-fused placeholder contains two complete side bases and requires `total_thickness_mm >= 2 × base_thickness_mm`.
- A fused build requires only a positive `total_thickness_mm`; it is independent of `base_thickness_mm`.

All numeric values must be finite. Width, height and fused body thickness must be positive; other thickness and relief values must be non-negative.

## Relief side settings

```json
{
  "enabled": true,
  "relief_height_mm": 3.0,
  "background_depth_mm": 0.0,
  "height_mode": "grayscale",
  "quality_mode": "standard",
  "invert_height": false,
  "mask_mode": "auto",
  "alpha_threshold": 1,
  "luminance_threshold": 20.0,
  "minimum_thickness_mm": 0.8,
  "crop_to_foreground": true,
  "crop_padding_px": 1,
  "uniform_height_normalized": 1.0,
  "smooth_strength": 0.0,
  "detail_sharpness": 0.0,
  "process_profile": "general",
  "manual_crop_box": null,
  "perspective_quad": null,
  "mask_edits": [],
  "region_layers": [],
  "semantic_annotations": [],
  "lock_confirmed_regions": true,
  "bezier_contours": [],
  "adaptive_mesh_enabled": true
}
```

Supported values:

- `mask_mode`: `auto`, `alpha`, `luminance`, `luminance-dark`, `luminance-light`.
- `height_mode`: `grayscale`, `layers`, `hybrid`.
- `quality_mode`: `preview`, `standard`, `high`.
- `process_profile`: `general`, `fdm`, `resin`, `cnc`, `mould`.
- `uniform_height_normalized`, `smooth_strength` and `detail_sharpness`: finite values in `0..1`.

`manual_crop_box` is `[x0, y0, x1, y1]` in the post-perspective source pixel grid. `perspective_quad` contains four normalized source points ordered top-left, top-right, bottom-right and bottom-left.

Mask edits are applied in source space before crop and resize. Region layers are applied after the final geometry crop.

Semantic annotations use the roles `void`, `base`, `low`, `mid`, `high`, `top`,
`raise` and `recess`. A record stores its source/final coordinate space, tool
(`part` or `brush`), point, radius, optional relative amount and lock state.
Locked fixed-level annotations are re-applied after automatic height operations
when `lock_confirmed_regions` is true.

Bezier contours store normalized anchors plus cubic `in`/`out` handles. Closed
contours are evaluated in saved order with `replace`, `add`, `remove` or
`intersect`. `adaptive_mesh_enabled` selects feature-local XY refinement for
straight-edge masked solids; discrete layer mode retains exact flat plateaus and
vertical steps.

## Edge and rim settings

```json
{
  "edge_style": "straight",
  "bevel_mm": 0.0,
  "radius_mm": 0.0,
  "rim_enabled": false,
  "rim_width_mm": 0.0,
  "rim_width_px": 0,
  "rim_height_mm": 0.0,
  "rim_profile": "flat",
  "contour_smoothing_iterations": 1
}
```

Supported `edge_style` values are `straight`, `sloped`, `bevel` and `rounded`. The current mesh builder creates closed profiled boundary geometry. The heightmap rim remains a separate local height operation and reports clipping.

## Fused double-side settings

```json
{
  "enabled": false,
  "back_scale": 1.0,
  "back_rotation_deg": 0.0,
  "back_offset_x_mm": 0.0,
  "back_offset_y_mm": 0.0,
  "flip_back_horizontal": true,
  "footprint_mode": "union"
}
```

`footprint_mode` is one of `union`, `intersection`, `front` or `back`. The back image is interpreted as viewed from the back, optionally flipped horizontally, then scaled, rotated and offset before both fields are fused onto one shared body grid.

## Mask edit

```json
{
  "shape": "circle",
  "coordinate_space": "pixel",
  "x": 120.0,
  "y": 85.0,
  "radius_px": 10.0,
  "operation": "remove"
}
```

Mask edits support circle, rectangle and polygon geometry with `add`, `remove` or equivalent operation names. GUI clicks on the final mask preview are converted back to source pixels before persistence.

## Region layer

```json
{
  "shape": "circle",
  "coordinate_space": "final_normalized",
  "x": 0.5,
  "y": 0.5,
  "radius_normalized": 0.1,
  "height_normalized": 0.7,
  "locked": true
}
```

Region layers provide fixed normalized height plateaus. Locked layers are restored after global smoothing/sharpening.

## Manual height marker

```json
{
  "marker_type": "height",
  "target": "front",
  "data": {
    "shape": "circle",
    "coordinate_space": "final_normalized",
    "x": 0.5,
    "y": 0.5,
    "radius_normalized": 0.1,
    "operation": "add",
    "delta": 0.2
  },
  "created_at": "2026-07-10T00:00:00+00:00"
}
```

Supported targets are `front`, `back`, `both`, `heightmap` and `relief`. Supported operations include set, add, subtract and smooth. Supported shapes are circle/brush, rectangle and polygon/freeform.

Coordinate spaces include:

- `normalized`: normalized post-EXIF/perspective source coordinates;
- `pixel`: source pixels;
- `processed` / `processed_normalized`: resized processing grid;
- `final` / `final_normalized`: exact final tight geometry grid.

Malformed individual edits are ignored rather than terminating the complete project load. Build-time numeric and cross-field validation still rejects invalid project settings.

## Export record

```json
{
  "path": "example_assets/exports/example_front_standard.obj",
  "export_format": "obj",
  "created_at": "2026-07-10T00:00:00+00:00",
  "notes": "front relief standard",
  "report": {}
}
```

Project workflows choose a unique output name before writing. Mesh exporters use a temporary sibling file, flush/fsync and atomic replacement.

## Persistence guarantees

`save_project()`:

1. validates the supported version;
2. updates the timestamp;
3. serializes with `allow_nan=false`;
4. writes a temporary sibling file;
5. flushes and calls `fsync`;
6. atomically replaces the destination.

A serialization or write failure leaves the previous project file in place. The in-memory object may still contain unsaved changes.
