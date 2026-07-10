# `.medalproj` Project Format

A `.medalproj` file is UTF-8 JSON. It is project metadata, not a trusted executable format. Image, preview and export files are stored in the sibling `<project_stem>_assets/` directory.

## Versioning

The current supported `file_version` is `1`.

- Missing version is interpreted as the current version for legacy v1 files.
- Non-integer, zero or negative versions are rejected.
- A version greater than the current implementation is rejected with `UnsupportedProjectVersionError`.
- Unknown fields inside a supported version are ignored so additive forward-compatible metadata does not break v1 loading.
- No downgrade from a future version is attempted.

## Top-level structure

```json
{
  "name": "Example Medal",
  "file_version": 1,
  "created_at": "2026-07-10T00:00:00+00:00",
  "updated_at": "2026-07-10T00:00:00+00:00",
  "same_physical_object": true,
  "front_image": null,
  "back_image": null,
  "reference_images": [],
  "outline": {},
  "dimensions": {},
  "edge": {},
  "front_relief": {},
  "back_relief": {},
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

`path` is resolved relative to the project file directory and must remain inside the sibling project asset root after `resolve()`. Absolute paths and `..` components are not accepted when they resolve outside that root. The original source path is informational only and is not used as the build asset.

## Dimensions

```json
{
  "width_mm": 80.0,
  "height_mm": 60.0,
  "total_thickness_mm": 4.0,
  "base_thickness_mm": 2.0
}
```

- Width and height must be finite and greater than zero.
- Base thickness must be finite and non-negative.
- A single-side build requires total thickness to be at least one base thickness.
- A double placeholder requires total thickness to be at least two base thicknesses.
- `total_thickness_mm` is currently a double-side body/spacing budget, not a guarantee of placeholder final bbox thickness.

## Relief side settings

```json
{
  "enabled": true,
  "relief_height_mm": 3.0,
  "background_depth_mm": 0.0,
  "layer_count": 4,
  "height_mode": "grayscale",
  "quality_mode": "standard",
  "invert_height": false,
  "mask_mode": "auto",
  "alpha_threshold": 1,
  "luminance_threshold": 20.0,
  "minimum_thickness_mm": 0.8,
  "crop_to_foreground": true,
  "crop_padding_px": 1
}
```

Supported mask modes are `auto`, `alpha`, `luminance`, `luminance-dark` and `luminance-light`.

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
  "use_smoothed_side_walls": false,
  "contour_smoothing_iterations": 1
}
```

`bevel_mm` and `radius_mm` are reserved persisted parameters; true bevel/rounded geometry is not yet implemented. The current rim is a heightmap boost, and clipping is reported.

## Manual marker

```json
{
  "marker_type": "height",
  "target": "front",
  "data": {
    "shape": "circle",
    "coordinate_space": "normalized",
    "x": 0.5,
    "y": 0.5,
    "radius_normalized": 0.1,
    "operation": "add",
    "delta": 0.2
  },
  "created_at": "2026-07-10T00:00:00+00:00"
}
```

Supported targets include front, back, both, heightmap and relief. Supported shapes are circle, rectangle and polygon. Supported operations are set, add and subtract.

Coordinate spaces:

- normalized original-image coordinates;
- original-image pixels;
- resized processing-grid pixels;
- final geometry-grid pixels.

Malformed markers are ignored rather than terminating the complete build.

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

Project workflows select a unique output name before writing. Each history record should therefore point to a traceable output rather than a silently overwritten filename.

## Persistence guarantees

`save_project()`:

1. updates the project timestamp;
2. serializes with `allow_nan=false`;
3. writes a temporary sibling file;
4. flushes and calls `fsync`;
5. atomically replaces the destination.

A serialization or write failure leaves the previous project file in place. The in-memory object may still have an updated timestamp and should be considered unsaved until the next successful save.
