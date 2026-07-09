# Badge Relief Maker

Badge Relief Maker is an experimental Windows-first desktop tool for converting 2D images of badges, medals, crests, emblems, award plates and relief-style decorative designs into editable 3D relief meshes.

The project is not intended to be a general-purpose AI image-to-3D system. Its first target is narrower and more practical: take one front image, or a front/back image pair, extract the visible face details, build layered relief height, add thickness and side closure, and export a manufacturable base model for Blender, 3D printing, CNC engraving, mould design or further manual refinement.

## Current scope

The first implementation prioritizes local/offline processing so it can run on ordinary Windows laptops. Heavy image-to-3D AI models, cloud APIs and GPU servers are intentionally outside the MVP.

The project now has these layers:

- A project layer that can create, save and open `.medalproj` JSON files with a sibling asset folder.
- A project-aware side relief workflow that imports front or back images, builds rough side meshes and records export history.
- A double-side placeholder workflow that places front and mirrored back relief meshes into one combined OBJ/STL for Blender inspection.
- A split OBJ exporter for Blender-friendly front/back object separation.
- A single-side relief pipeline that can generate a rough OBJ or ASCII STL from one image.
- A lightweight outline report, contour side wall builder, optional smoothed side wall builder, outer rim height boost with flat/linear/smooth profiles, mesh repair pass and topology report for early warnings.

The current runnable mesh path is a simple single-side proof of concept:

- Load one image.
- Build a foreground mask.
- Remove small isolated mask fragments.
- Fill small enclosed mask holes.
- Optionally smooth mask noise with a small majority filter.
- Crop to the foreground bounding box.
- Downsample very large masks before mesh generation.
- Optionally apply an outer rim height boost along the foreground boundary.
- Support flat, linear or smooth rim height profiles.
- Extract outline boundary metrics from the final mask.
- Trace boundary loops, remove collinear contour points and calculate smoothed-loop metrics.
- Convert brightness to a heightmap.
- Build a masked footprint relief solid by default.
- Add base thickness and contour-driven external side walls.
- Optionally use experimental smoothed contour side walls.
- Add internal vertical walls where neighboring relief cells have different heights.
- Deduplicate repeated vertices.
- Run basic mesh repair to remove invalid faces, zero-area faces, duplicate faces and unreferenced vertices.
- Export optional mask and heightmap previews.
- Export OBJ or ASCII STL.
- Return a basic manufacturing report with size, outline, rim, topology, repair metadata and warning fields.

The `.medalproj` file stores project name, front image, back image, reference images, same-object flag, outline state, dimensions, edge parameters, relief parameters, manual correction markers and export history. This is required so a front-only project can later receive a back image without starting over.

Quality modes are available for project builds: preview, standard and high. They currently map to different grid-size and mask-cleanup presets, not to a full sculpting engine.

The back-side workflow is currently incremental but independent: a back image can be added to an existing project and exported as its own back relief OBJ/STL.

The double-side placeholder workflow requires both front and back images. It combines the generated front relief and a mirrored generated back relief into one output file, but it is explicitly not a fused production body yet. OBJ placeholder export writes named objects `front_relief` and `back_relief` so Blender users can select and edit the two sides separately.

The outline report counts mask boundary edges, horizontal and vertical boundary edges, estimated boundary length, boundary loop counts, simplified contour point counts, smoothed contour point counts and a rough outline type label. The contour side wall builder uses the external mask boundary as a separate side-wall layer. The optional smoothed side wall path can already export experimental smoother walls, but it may need Blender cleanup because it does not yet share vertices perfectly with the pixel-cell top surface.

The outer rim height boost raises foreground cells near the mask boundary before mesh generation. Flat profile raises all rim cells equally; linear profile tapers the rim inward with a straight ramp; smooth profile uses a smoothstep ramp for a softer rounded-looking transition. This is a simple way to create a badge-like raised border; it is not yet a true bevelled or rounded rim mesh.

The topology report counts unique edges, boundary edges and non-manifold edges. The repair pass removes simple invalid or redundant geometry. These are lightweight diagnostics and cleanup steps, not proof that a mesh is production-ready.

The masked footprint mode follows transparent foreground pixels, so it is closer to a badge outline than the first rectangular proof of concept. It is still intentionally simple and uses one solid cell per foreground pixel.

Internal height step closure is now included so adjacent high and low relief cells do not leave obvious vertical cracks in the MVP mesh.

The report is advisory only. It currently includes vertex count, face count, bounding box, estimated total thickness, crop/resize metadata, mask cleanup metadata, outline metadata, rim metadata, repair metadata, topology metadata and early warnings. It does not yet prove that a model is watertight or production safe.

The intended MVP still includes stronger side/rim generation, stronger mesh repair, GLB export, richer desktop UI and later fused double-side mode.

## Planned modes

### Single-side mode

Input one front image and generate a raised relief surface with a flat back, base plate, mirrored back, or simple reverse impression.

### Double-side mode

Input one front image and one back image, align both sides, generate relief for each side, connect them by a controlled thickness, and output a closed solid.

### Reference mode

Input similar-object images as references without assuming that front and back belong to the same physical object.

## Project workflow

Create a project file:

```bash
python -m badge_relief_maker.app --new-project "Test Medal" --project-path test.medalproj
```

This creates:

```text
test.medalproj
test_assets/
  images/
  previews/
  exports/
```

Import a front image into the project:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --import-front front.png
```

Build front relief from the project and record export history:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --build-front --project-export-format obj --quality preview
```

Add a back image later to the same project:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --import-back back.png
```

Build back relief from the same project and record export history:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --build-back --project-export-format stl --quality preview
```

Build a combined front/back placeholder assembly:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --build-double-placeholder --project-export-format obj --quality preview
```

The placeholder assembly is useful for Blender inspection and layout checking. It is not a finished fused double-side production model. When the placeholder is exported as OBJ, the file contains named object sections for `front_relief` and `back_relief`.

A generic side build form is also available:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --build-side front --project-export-format obj --quality standard
```

Import a reference image without treating it as the same physical object:

```bash
python -m badge_relief_maker.app --project-path test.medalproj --import-reference ref.png --reference-role same_type_front
```

Run the GUI skeleton if PySide6 is installed:

```bash
python -m badge_relief_maker.app --gui
```

Install optional GUI dependency:

```bash
pip install -r requirements-gui.txt
```

## Direct CLI proof of concept

Export OBJ without a project file:

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --width-mm 80 --height-mm 80 --base-mm 2 --relief-mm 3
```

Export ASCII STL without a project file:

```bash
python -m badge_relief_maker.app --input input.png --output output.stl --width-mm 80 --height-mm 80 --base-mm 2 --relief-mm 3
```

Use experimental smoothed side walls:

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --smoothed-side-walls --contour-smoothing-iterations 1
```

Add a simple raised outer rim:

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --rim-width-px 2 --rim-height-mm 1.0 --rim-profile smooth
```

To export mask and heightmap preview images:

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --preview-dir previews
```

To control crop, grid size and mask cleanup:

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --crop-padding-px 2 --max-grid-cells 20000 --min-component-pixels 8 --fill-hole-pixels 16 --mask-smooth-iterations 1
```

Use the rectangular debugging fallback when needed:

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --rectangle-footprint
```

Disable foreground crop when debugging full image scale:

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --no-crop
```

These commands should be treated as first pipeline tests, not production-grade model generation.

## Suggested development order

1. Add bevel/rim mesh parameters beyond heightmap boosting.
2. Add stronger mesh repair and hole-fill actions.
3. Add GLB export.
4. Expand PySide6 UI panels.
5. Add fused double-side alignment and solid generation.
6. Add region-based manual height editing.
