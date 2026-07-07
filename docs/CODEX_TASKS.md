# Codex Tasks

This file is the execution guide for future Codex work. Do not turn this project into a general AI image to 3D application. Build the local relief pipeline first.

## Task 1: Make the single image pipeline runnable

Status: first version implemented.

Input:

- A local PNG path
- Width in mm
- Height in mm
- Relief height in mm

Output:

- Vertices and faces
- OBJ file
- Build report

Acceptance:

- A small test image produces a non empty mesh.
- OBJ file contains vertex and face records.
- Smoke test passes.

## Task 2: Add mask preview assets

Input:

- RGBA image

Output:

- Foreground mask
- Mask preview image

Acceptance:

- Transparent areas become background.
- Foreground is visible in preview.

## Task 3: Add base and side closure

Status: first masked footprint version implemented.

Input:

- Heightmap
- Foreground mask
- Base thickness
- Total dimensions

Output:

- Mask footprint relief solid

Acceptance:

- The mesh has a back plate.
- Side walls connect the front surface to the back plate.
- Exported OBJ can be opened by Blender.

Next refinement:

- Replace per-pixel solid cells with contour-based side closure.
- Remove duplicate vertices.
- Smooth stair-step boundaries.

## Task 4: Add STL and GLB export

Input:

- Mesh data
- Export path

Output:

- OBJ
- STL
- GLB

Acceptance:

- Unsupported extensions fail with clear error.
- Exported files are written to the selected output folder.

## Task 5: Add manufacturing report

Report fields:

- Vertex count
- Face count
- Bounding box size
- Thickness parameters
- Open edge warning if available
- Minimum feature warning if available

Acceptance:

- The report is returned after every build.
- Warnings use cautious language.

## Task 6: Add GUI shell

Panels:

- Image import
- Preview
- Parameters
- Build and export
- Warnings

Acceptance:

- GUI launches on Windows.
- User can select image and output folder.
- Buttons call existing core functions.

## Task 7: Add double side mode later

Do this only after single side MVP works.

Input:

- Front image
- Back image
- Alignment settings
- Total thickness

Output:

- One combined model

Acceptance:

- Front and back test patterns are both visible.
- The model uses one shared output scale.

## Rules for every change

- Keep local offline operation working.
- Do not require cloud APIs.
- Do not require high end GPU.
- Do not bind to Paint 3D.
- Keep Blender as optional downstream workflow.
- Add or update tests when adding core functions.
