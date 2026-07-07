# Project Plan

## Product definition

Badge Relief Maker is a local desktop assistant for turning 2D badge and relief artwork into 3D relief base models. It should not attempt to infer a complete unknown 3D object from one image. It should focus on reproducing the visible front/back faces as layered relief surfaces and producing a closed, editable and manufacturable mesh.

## Target objects

- Badges
- Medals
- Crests
- Award plaques
- Decorative plates
- Emblems
- Relief graphics
- Designs with clear front/back faces

## Non-goals

- Full AI image-to-3D reconstruction
- Human/character sculpting
- Complex mechanical reconstruction
- Transparent or reflective object reconstruction
- Cloud-first SaaS
- Paint 3D dependency
- Blender replacement

## Architecture

```text
Image input
  -> preprocessing
  -> mask generation
  -> contour/region extraction
  -> heightmap generation
  -> relief mesh builder
  -> side/base builder
  -> mesh repair/checks
  -> export
```

## Core modules

- `image_preprocess.py`: load images, crop, normalize and remove simple backgrounds.
- `mask_generator.py`: create binary foreground masks.
- `contour_extractor.py`: detect outer and internal contours.
- `heightmap_generator.py`: build continuous or layered heightmaps.
- `relief_mesh_builder.py`: convert heightmaps into mesh surfaces.
- `double_side_builder.py`: combine front and back reliefs into one solid.
- `mesh_repair.py`: smooth, clean, repair normals and simplify.
- `mesh_exporter.py`: export STL, OBJ and GLB.
- `manufacturability_check.py`: report watertightness, face count and basic warnings.

## MVP parameters

- Width in mm
- Height in mm
- Total thickness in mm
- Base thickness in mm
- Front relief max height in mm
- Back relief max height in mm
- Smooth strength
- Edge sharpness
- Minimum printable thickness

## Double-side requirements

The double-side mode should support manual alignment first, then automatic alignment later. Required controls:

- Center alignment
- Scale alignment
- Rotation adjustment
- X/Y offset
- Front relief height
- Back relief height
- Total thickness
- Side style: straight, bevel, rounded

## Risk areas

1. Complex artwork may need manual masking.
2. Text and fine engraved lines may be too thin for manufacturing.
3. Height from brightness is only an approximation.
4. A closed mesh is not automatically manufacturable; minimum thickness still matters.
5. Double-side images may not be in the same scale or perspective.
6. Heavy AI models should remain optional because target machines may only have laptop GPUs.
