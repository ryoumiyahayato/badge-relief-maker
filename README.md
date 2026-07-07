# Badge Relief Maker

Badge Relief Maker is an experimental Windows-first desktop tool for converting 2D images of badges, medals, crests, emblems, award plates and relief-style decorative designs into editable 3D relief meshes.

The project is not intended to be a general-purpose AI image-to-3D system. Its first target is narrower and more practical: take one front image, or a front/back image pair, extract the visible face details, build layered relief height, add thickness and side closure, and export a manufacturable base model for Blender, 3D printing, CNC engraving, mould design or further manual refinement.

## Current scope

The first implementation prioritizes local/offline processing so it can run on ordinary Windows laptops. Heavy image-to-3D AI models, cloud APIs and GPU servers are intentionally outside the MVP.

The current runnable path is a simple single-side proof of concept:

- Load one image.
- Build a foreground mask.
- Convert brightness to a heightmap.
- Build a rectangular solid relief mesh.
- Add base thickness and side walls.
- Export OBJ.

The intended MVP still includes contour trimming, stronger mesh repair, STL/GLB export, a desktop GUI and later double-side mode.

## Planned modes

### Single-side mode

Input one front image and generate a raised relief surface with a flat back, base plate, mirrored back, or simple reverse impression.

### Double-side mode

Input one front image and one back image, align both sides, generate relief for each side, connect them by a controlled thickness, and output a closed solid.

## CLI proof of concept

```bash
python -m badge_relief_maker.app --input input.png --output output.obj --width-mm 80 --height-mm 80 --base-mm 2 --relief-mm 3
```

This command currently exports OBJ only. It uses a rectangular footprint and should be treated as a first pipeline test, not a production-grade model.

## Suggested development order

1. Improve single-side relief generation from a clean PNG.
2. Add contour-based footprint trimming.
3. Add STL and GLB export.
4. Add mesh repair and manufacturing checks.
5. Add simple PySide6 GUI.
6. Add double-side alignment and solid generation.
7. Add region-based manual height editing.
8. Add optional AI-assisted segmentation or cleanup.
