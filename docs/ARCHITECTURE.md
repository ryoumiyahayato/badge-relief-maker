# Architecture

## Pipeline

```text
Input image
  -> image preprocess
  -> mask generation
  -> contour extraction
  -> heightmap generation
  -> relief mesh building
  -> base and side closure
  -> mesh repair
  -> manufacturing report
  -> export
```

## Module responsibilities

### image_preprocess

Loads images, normalizes format, handles crop and prepares RGBA data.

### mask_generator

Creates foreground masks from alpha, luminance, color key or manual user corrections.

### contour_extractor

Finds outer contour and internal regions. Later versions should use OpenCV or scikit image for connected components, edges and region boundaries.

### heightmap_generator

Builds the 2D height field used for relief. It should support brightness mode, layer mode and hybrid mode.

### relief_mesh_builder

Converts a heightmap to vertices and faces. The early version can use a regular grid. Later versions should reduce unnecessary triangles outside the mask and preserve sharp edges.

### double_side_builder

Aligns front and back data, then connects both sides with total thickness and generated side walls.

### mesh_repair

Handles cleanup, duplicate removal, smoothing, simplification, normal repair, hole filling and small part removal.

### manufacturability_check

Produces warnings for manufacturing use. It should not claim the model is guaranteed safe. It should report measurable risks.

### mesh_exporter

Exports OBJ first because it is easy to verify. STL and GLB should follow through trimesh or another mesh library.

### ui

The desktop interface should expose simple terms: import image, crop, mask preview, relief height, base thickness, total thickness, generate, repair, export.

## Data objects

### ReliefParameters

Suggested fields:

- width_mm
- height_mm
- total_thickness_mm
- base_thickness_mm
- front_relief_height_mm
- back_relief_height_mm
- edge_radius_mm
- bevel_mm
- smooth_strength
- detail_sharpness
- minimum_thickness_mm

### ReliefBuildResult

Suggested fields:

- vertices
- faces
- report
- warnings
- export_paths

## Implementation strategy

Start with a small deterministic pipeline:

1. Load a clean transparent PNG.
2. Generate a mask from alpha.
3. Generate a simple heightmap.
4. Build a front grid surface.
5. Add a flat base and side walls.
6. Export OBJ.
7. Add STL and GLB.

Only after this works should the project add advanced segmentation, manual region editing and double side generation.

## Constraints

- Local offline first.
- No required cloud API.
- No required heavy AI model.
- No Paint 3D dependency.
- Blender is a downstream editor, not a dependency for MVP.
