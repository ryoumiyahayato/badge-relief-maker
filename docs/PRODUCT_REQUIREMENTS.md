# Product Requirements

## Goal

Build a Windows local offline desktop tool that converts 2D artwork of badges, medals, crests, award plates, nameplates and relief ornaments into editable 3D relief models.

The tool is not a general image to 3D system. It should focus on visible front and back faces, layered relief height, controlled thickness, side closure and export for later manufacturing.

## Core principle

The first version should reproduce the face shown in the image. It should not guess an unknown full 3D object. Side walls can be generated from parameters.

## Target objects

- Badges
- Medals
- Awards
- Crests
- Nameplates
- Decorative plates
- Relief artwork
- Objects with clear front and optional back artwork

## Out of scope

- General AI image to 3D
- Complex character sculpture
- Complex mechanical reconstruction
- Transparent objects
- Highly reflective real objects
- Cloud first product
- Login or account system
- Mobile app
- Paint 3D dependency
- Blender replacement

## Inputs

- One front image
- Optional back image
- JPG and PNG first
- Manual crop support
- Foreground mask preview
- Contour preview
- Optional manual mask cleanup later

## Outputs

- STL for printing and mould workflows
- OBJ for Blender and common 3D tools
- GLB for preview and material aware workflows
- 3MF can be added later

## Single side mode

When only the front image is available, the tool should:

1. Load the front image.
2. Extract the foreground mask.
3. Extract the outer contour and internal detail regions.
4. Generate a heightmap.
5. Build a front relief mesh.
6. Add base thickness.
7. Generate side walls.
8. Close the model where possible.
9. Export the result.

Back options:

- Flat back
- Simple base plate
- Mirrored back
- Reverse impression

## Double side mode

When front and back images are available, the tool should:

1. Process both images separately.
2. Generate front and back heightmaps.
3. Align center, scale, rotation and outer contour.
4. Connect both relief faces through total thickness.
5. Generate side walls.
6. Produce one closed solid.

Side options:

- Straight edge
- Sloped edge
- Rounded edge
- Beveled edge

## Height generation modes

### Grayscale heightmap

Brightness becomes height. The user can invert the mapping.

### Region layer mode

Detected or user selected regions receive explicit heights. Example layer plan:

- Base: 0 mm
- Main body: 1 mm
- Letters or emblem: 2 mm
- Leaves and ornaments: 2.5 mm
- Top ornament: 3 mm

### Hybrid mode

The program creates an initial heightmap and the user adjusts global height, local height, smooth strength and edge sharpness.

## Required parameters

- Final width in mm
- Final height in mm
- Total thickness in mm
- Base thickness in mm
- Front relief max height in mm
- Back relief max height in mm
- Edge radius
- Edge bevel
- Smooth strength
- Detail sharpness
- Minimum thickness warning value

## Basic repair and manufacturing checks

The first useful version should report:

- Vertex count
- Face count
- Current size in mm
- Total thickness
- Open edges if detectable
- Very thin features if detectable
- Floating small parts if detectable
- Whether STL export is likely safe

## Blender workflow

The tool only creates a base model. Final detail cleanup can be done in Blender or other 3D tools. Exported STL, OBJ and GLB must be importable by Blender.

## Hardware constraint

The user may only have an RTX 3050 Ti Laptop with 8 GB VRAM. The MVP must not require heavy local AI models, cloud APIs or high end GPU hardware. Traditional image processing and geometry should be the main path.
