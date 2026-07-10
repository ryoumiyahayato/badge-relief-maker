# Badge Relief Maker

Badge Relief Maker is an experimental Windows-first local tool for converting 2D badge, medal, crest, emblem and award artwork into editable 2.5D relief meshes for Blender, 3D printing, CNC work, mould design and manual refinement.

It is not a general AI image-to-3D system and does not promise an automatic production-perfect replica. The current target is a deterministic local pipeline that produces a repairable base mesh from one front image or a front/back project.

## Installation and entry point

The repository root is the only supported Python package root.

```bash
python -m pip install -e .
python -m badge_relief_maker.app
```

Install test dependencies and run the suite:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

The obsolete nested placeholder package and its old core modules have been removed from the runnable path.

## Current pipeline

The single-side build path now performs the following steps:

- Load JPG or PNG as RGBA.
- Select an explicit `alpha`, `luminance` or `auto` foreground-mask mode.
- In `auto` mode, use alpha only when it contains useful transparency variation; otherwise compare luminance against the image border, supporting both dark-on-light and light-on-dark artwork.
- Remove small components, fill small holes and optionally smooth the mask.
- Generate a grayscale heightmap normalized only from masked foreground pixels.
- Crop and resize the processing grid.
- Transform saved manual markers from original-image coordinates through crop and resize.
- Apply circular, rectangular or polygon height edits.
- Tight-crop the geometry mask so processing padding does not change final physical dimensions.
- Convert rim width in millimeters using the actual final grid rather than a quality-preset estimate.
- Build a closed indexed height-field solid with shared top, bottom and wall vertices.
- Preserve separate vertex namespaces for disconnected mask components instead of globally merging coincident vertices.
- Run conservative face and unreferenced-vertex repair.
- Report boundary edges, non-manifold edges, inconsistent edge winding, face areas, whole-mesh signed volume, disconnected components and per-component signed volumes.
- Export OBJ, ASCII STL or binary GLB.

For a masked build, the foreground bounding box is scaled to the requested `width_mm × height_mm`. Crop padding affects image processing only, not the finished XY size.

The indexed height-field surface averages incident cell heights at shared corners. Adjacent cells therefore share one continuous top edge instead of separate plateaus connected by T-junction-prone step walls. The manufacturing path currently favors this closed surface over the older experimental smoothed-wall output. When smoothed walls are requested, the build defers them and keeps the closed indexed solid.

## Project files

A `.medalproj` file stores project metadata, front and back assets, reference images, dimensions, edge settings, relief settings, manual markers and export history.

Project handling includes:

- Atomic JSON saves through a temporary file and replace operation.
- Sanitized asset roles and filenames.
- Resolved-path containment checks that prevent image imports or stored asset paths from escaping the project directory.
- Unique imported asset filenames instead of silent overwrite.
- Unique export filenames so multiple history entries do not point to the same overwritten file.
- Explicit parsing of saved boolean strings.
- Numeric and cross-field validation before project builds.
- A single-side thickness rule requiring total thickness to accommodate one base layer.
- A double-side thickness rule requiring total thickness to accommodate two base layers.
- Filtering of malformed nested project records and malformed manual markers.

Create a project:

```bash
python -m badge_relief_maker.app --new-project "Test Medal" --project-path test.medalproj
```

Import front and back images:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --import-front front.png
python -m badge_relief_maker.app --project-path test.medalproj --import-back back.png
```

Import a reference image:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --import-reference ref.png --reference-role same_type_front
```

Build one side:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --build-front --project-export-format obj --quality preview
python -m badge_relief_maker.app --project-path test.medalproj --build-side back --project-export-format glb --quality standard
```

Build the front/back inspection assembly:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --build-double-placeholder --project-export-format glb --quality preview
```

The generic side-build wrapper used by the CLI is part of `project_build.py`. The back mesh is reflected across Z and its triangle winding is reversed so the reflection does not turn outward normals inward.

The double-side result is still an inspection placeholder, not a fused production body. OBJ and GLB preserve named `front_relief` and `back_relief` parts.

## Direct image builds

```bash
python -m badge_relief_maker.app \
  --input input.jpg \
  --output output.obj \
  --width-mm 80 \
  --height-mm 80 \
  --base-mm 2 \
  --relief-mm 3 \
  --mask-mode auto
```

Force luminance masking for an opaque scan or photograph:

```bash
python -m badge_relief_maker.app --input scan.jpg --output scan.stl --mask-mode luminance --luminance-threshold 20
```

Force alpha masking for a transparent PNG:

```bash
python -m badge_relief_maker.app --input artwork.png --output artwork.glb --mask-mode alpha
```

Add a simple heightmap rim:

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --rim-width-px 2 --rim-height-mm 1.0 --rim-profile smooth
```

Export previews:

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --preview-dir previews
```

The CLI rejects conflicting primary actions instead of silently choosing one import or build option.

## Manual marker coordinates

Project marker coordinates are interpreted in the original source image:

```text
original image coordinates
→ processing crop
→ grid resize
→ final geometry crop
→ millimeter mesh
```

Normalized marker coordinates are relative to the original image. Pixel centers, pixel radii, rectangular dimensions and polygon points are transformed before the marker is applied. Already processed coordinates may opt out with `coordinate_space: "processed"` or `"heightmap"`.

Supported marker shapes and operations include:

- Circle/brush: `x`, `y`, `radius_px` or `radius_normalized`.
- Rectangle: center plus pixel dimensions, or explicit normalized region dimensions such as `width_normalized` and `region_height_normalized`.
- Polygon/freeform: `points`, `vertices` or `polygon_points`.
- Operations: set, add and subtract.

`height_normalized` is the target relief value, not the normalized rectangle height.

## GLB output

GLB output contains glTF 2.0 positions, vertex normals, triangle indices and simple PBR material records. Multi-object GLB keeps separate named nodes and materials. UVs and textures are not implemented yet.

OBJ, STL and GLB share the same mesh-array validation: vertices and faces must be finite `N×3` arrays, face indices must be integers, and indices must stay inside the vertex array.

## Manufacturing status

Representative non-uniform and disconnected-component regression cases now require:

- zero open boundary edges;
- zero non-manifold edges;
- zero inconsistent-winding edges;
- positive signed volume for outward-oriented closed components;
- per-component orientation reporting so opposite signed volumes cannot hide each other in a whole-mesh total;
- requested foreground XY dimensions after crop and processing padding.

This remains an advisory MVP, not a manufacturing certification system. Direct manufacturing output is not recommended until the full automated suite and representative Blender/slicer/CAM checks pass, and until the following are implemented:

1. True bevelled or rounded rim geometry.
2. Hole filling, self-intersection detection/repair and automatic component-level orientation repair.
3. Fused and aligned front/back production solids.
4. Text, motif and decorative-region separation.
5. Higher-quality contour and layer generation.
6. Visual GUI editing for masks, polygons, brushes and local height locks.
7. UV and texture export.
8. Physical validation against real print/CNC tolerances.
