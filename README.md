# Badge Relief Maker

Badge Relief Maker is an experimental Windows-first desktop tool for converting 2D images of badges, medals, crests, emblems, award plates and relief-style decorative designs into editable 3D relief meshes.

The project is not intended to be a general-purpose AI image-to-3D system. Its first target is narrower and more practical: take one front image, or a front/back image pair, extract the visible face details, build layered relief height, add thickness and side closure, and export a manufacturable base model for Blender, 3D printing, CNC engraving, mould design or further manual refinement.

## Current scope

The first implementation should prioritize local/offline processing so that it can run on ordinary Windows laptops. Heavy image-to-3D AI models, cloud APIs and GPU servers are intentionally outside the MVP.

The intended MVP focuses on:

- JPG/PNG import.
- Foreground mask generation.
- Contour and region extraction.
- Heightmap generation from image brightness or region layers.
- Single-face relief mesh creation.
- Base thickness and simple side closure.
- Mesh repair checks.
- STL/OBJ/GLB export.

## Planned modes

### Single-side mode

Input one front image and generate a raised relief surface with a flat back, base plate, mirrored back, or simple reverse impression.

### Double-side mode

Input one front image and one back image, align both sides, generate relief for each side, connect them by a controlled thickness, and output a closed solid.

## Repository status

This repository currently contains the project scaffold, module layout, placeholder implementations and planning documents. It is not a finished application yet.

## Suggested development order

1. Single-side relief generation from a clean PNG.
2. Mesh export and basic manufacturing checks.
3. Simple PySide6 GUI.
4. Double-side alignment and solid generation.
5. Region-based manual height editing.
6. Optional AI-assisted segmentation or cleanup.

## Run placeholder entry point

```bash
python -m badge_relief_maker.app
```

At this stage, the command only verifies that the package entry point exists.
