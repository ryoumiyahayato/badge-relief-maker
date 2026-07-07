# Implementation Notes

## First technical target

The first useful target is not perfect modelling. It is a deterministic proof of concept:

```text
clean PNG -> mask -> heightmap -> relief surface -> base -> OBJ
```

This proves that the project direction works without heavy AI or cloud services.

## Image assumptions for MVP

MVP can assume:

- Clear front image
- Transparent or high contrast background
- Object roughly centered
- No perspective correction yet
- No automatic historical reconstruction

## Heightmap strategy

Start with two simple options:

1. Alpha mask gives the footprint.
2. Brightness or a constant value gives height.

Then add layer editing. Region based height control is more important than AI in this project because badges and medals often need intentional manufacturing exaggeration.

## Mesh strategy

Start with a regular grid because it is simple and testable. Later improve it by:

- Removing triangles outside the mask
- Simplifying flat regions
- Preserving sharp borders
- Adding bevels and rounded edges
- Using contour extrusion for cleaner side walls

## Manufacturing reality

Fine text, tiny scratches and thin decorative lines may not be physically manufacturable at original visual scale. The program should warn users instead of pretending every pixel can be produced.

## Suggested libraries later

The early scaffold avoids hard dependency on heavy packages. Later implementation can add:

- OpenCV for contours and morphology
- scikit image for segmentation
- trimesh for export and mesh utilities
- pymeshlab for repair and simplification
- PySide6 for desktop GUI
- PyInstaller or Nuitka for Windows packaging

## Quality rule

When a feature is uncertain, prefer explicit user parameters over hidden guessing. This is a manufacturing assistant, not an automatic fantasy object generator.
