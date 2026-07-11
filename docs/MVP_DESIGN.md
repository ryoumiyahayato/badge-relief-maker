# MVP Design

`docs/BASELINE_V1.md` is the acceptance source of truth. This document describes the current technical design for the single-side MVP.

## Product boundary

Badge Relief Maker is a Windows local/offline 2.5D relief base-model generator. It should automate a large part of outline, base, coarse-height and export work, while leaving artistic correction and production preparation to Blender or other manufacturing software.

Out of scope for the single-side MVP:

- general image-to-complete-3D reconstruction;
- cloud-only or GPU-heavy AI;
- guaranteed manufacturing-ready output;
- automatic recovery of true physical depth from brightness;
- fused production double-side geometry;
- process-independent claims of print, CNC or mould safety.

## Supported workflow

```text
open/create .medalproj or direct image build
-> EXIF-aware image load
-> alpha/luminance foreground mask
-> deterministic mask cleanup
-> foreground-only grayscale heightmap
-> ImageTransform coordinate chain
-> manual circle/rectangle/polygon height edits
-> tight geometry crop and physical scaling
-> optional heightmap rim
-> closed indexed relief solid
-> conservative repair
-> advisory manufacturing report
-> atomic OBJ/STL/GLB export
```

## Module responsibilities

### Application layer

- `app/main.py`: CLI parsing, action exclusivity and readable command errors.
- `app/ui/main_window.py`: optional PySide6 project shell, parameter controls and worker-thread build dispatch.

### Project layer

- `project_model.py`: versioned project dataclasses and tolerant parsing of known fields.
- `project_io.py`: strict version ceiling, atomic save, unique assets, path containment and export history.
- `project_build.py`: conversion from persisted project settings to runtime parameters and project export workflows.

### Image and coordinate layer

- `image_preprocess.py`: EXIF orientation, RGBA conversion and source metadata.
- `mask_generator.py`: alpha, contrast, dark and light foreground modes.
- `mask_processing.py`: component cleanup, hole filling, smoothing, crop and downsampling.
- `image_transform.py`: original-image, crop, resized-grid, geometry-grid and millimeter transform record.
- `marker_transform.py`: applies the shared transform to all marker geometry.

### Relief and mesh layer

- `heightmap_generator.py`: foreground-only normalized grayscale height.
- `height_markers.py`: set/add/subtract operations for circle, rectangle and polygon regions.
- `rim_builder.py`: heightmap rim and clipping metadata.
- `masked_solid_builder.py`: shared-index closed masked height-field solid.
- `solid_builder.py`: rectangular solid path using the same indexed builder.
- `mesh_repair.py`: conservative invalid, zero-area, duplicate-face and unused-vertex cleanup.
- `manufacturability_check.py`: edge, winding, area, volume, component and advisory gate reports.
- `mesh_exporter.py`: shared mesh validation and atomic OBJ/STL/GLB writing.

## Coordinate contract

All array shapes use `(rows, columns)` and all geometric coordinates use `(x, y)`.

`ImageTransform` records:

1. EXIF-oriented original shape;
2. processing crop box in original-image pixels;
3. cropped shape;
4. resized processing-grid shape;
5. final tight geometry crop in processing-grid pixels;
6. final geometry shape.

Marker coordinate spaces:

- omitted/`normalized`: normalized original-image coordinates;
- `pixel`/`image_pixel`: original-image pixel coordinates;
- `processed`/`heightmap`: resized processing-grid pixels before final tight crop;
- `final`: final geometry-grid pixels.

The final tight crop changes position but not radius or width scale. Physical width and height are applied only after the final geometry grid is known.

## Mesh contract

A successful exported single-side mesh must use finite `N×3` vertices and integer triangular faces with valid indices. The checked topology must have:

- zero boundary edges;
- zero non-manifold edges;
- zero inconsistent-winding edges;
- zero invalid face references;
- zero zero-area faces;
- at least one closed oriented component;
- no inward closed components.

The current indexed height field uses shared corner heights and therefore produces a continuous top surface. It does not preserve exact sharp jumps between adjacent source pixels. A future constrained mesh mode is required for sharp steps.

## Physical dimensions

For a masked footprint, the final foreground grid maps to the requested width and height. Processing padding is not part of the product dimensions. Quality modes may change grid density but must not change physical size.

`base_thickness_mm` defines the flat one-side base. A single-side output thickness is the base plus generated relief actually present. `total_thickness_mm` is currently a double-side body/spacing budget and must not be interpreted as a guaranteed final placeholder bbox.

## Mask behavior

- `alpha`: use visible alpha pixels.
- `luminance`: absolute brightness difference from border background.
- `luminance-dark`: pixels darker than border background.
- `luminance-light`: pixels lighter than border background.
- `auto`: use alpha only when alpha contains useful variation; otherwise use luminance contrast.

An empty cleaned mask blocks mesh export. The caller may still request diagnostic preview files.

## Export contract

OBJ, STL and GLB use the same array validation. Writers create parent directories, write a temporary sibling file, flush/fsync and atomically replace the destination. Project builds choose a unique output name before writing.

STL coordinates are millimeters by convention because STL has no unit field. Blender import size and normal direction still require recorded manual acceptance.

## Manufacturing gate

The report distinguishes:

- `blocked`: a known severe geometry defect is present;
- `review_required`: checked topology passed, but manufacturing is not certified.

The gate always sets `unattended_manufacturing_recommended` to false. Missing checks include self-intersection, local wall thickness, minimum feature size and process-specific tool access or overhang constraints.

## GUI scope

The current GUI shell persists core front parameters and runs builds in a worker thread. MVP completion still requires exact source/mask/heightmap previews, manual crop and mask editing, a dedicated report panel and unsaved-change handling.

## Double-side scope

Two double-side paths are intentionally distinct. The inspection placeholder contains two independently closed solids; its back is reflected across Z with reversed winding and it is always manufacturing-blocked. The fused path independently preprocesses both faces, applies viewed-back flip/scale/rotation/X-Y offsets on one float alignment grid, creates one shared central body and requires one closed final component.

A production double-side design must add center/scale/rotation/offset alignment, one shared central body, no overlapping internal shells, one final closed oriented component and one unambiguous total-thickness definition.
