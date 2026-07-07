# Project Plan

## Product definition

Badge Relief Maker is a local desktop assistant for turning 2D badge and relief artwork into 3D relief base models. It should not try to infer a fully accurate unknown object from one image. The first version should focus on reproducing the visible front or back face as a layered relief surface, adding controlled thickness, and exporting an editable base model.

## Target objects

- Badges
- Medals
- Crests
- Award plaques
- Decorative plates
- Emblems
- Relief graphics

## Non-goals

- Full AI image-to-3D reconstruction
- Character sculpting
- Complex mechanical reconstruction
- Cloud-first service
- Paint 3D dependency
- Blender replacement

## Architecture

```text
Image input
  -> preprocessing
  -> mask generation
  -> contour and region extraction
  -> heightmap generation
  -> relief mesh builder
  -> side and base builder
  -> mesh repair and checks
  -> export
```

## Core modules

- `image_preprocess.py`: load, crop and normalize input images.
- `mask_generator.py`: create foreground masks.
- `contour_extractor.py`: find outer shapes and internal detail regions.
- `heightmap_generator.py`: convert brightness or layers into height values.
- `relief_mesh_builder.py`: turn heightmaps into mesh surfaces.
- `double_side_builder.py`: align and combine front/back reliefs.
- `mesh_repair.py`: clean, smooth and simplify meshes.
- `mesh_exporter.py`: export OBJ first, then STL and GLB.
- `manufacturability_check.py`: report face counts, thickness risks and mesh warnings.

## MVP parameters

- Width in mm
- Height in mm
- Total thickness in mm
- Base thickness in mm
- Front relief height in mm
- Back relief height in mm
- Smooth strength
- Edge sharpness
- Minimum printable thickness

## Development order

1. Single-side relief from a clean PNG.
2. OBJ export and basic checks.
3. Simple PySide6 GUI.
4. Manual height editing.
5. Double-side alignment and solid generation.
6. Optional AI segmentation or cleanup.
