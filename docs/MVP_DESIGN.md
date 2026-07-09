# MVP Design

## Part 1: Requirement understanding

This project is a local Windows desktop tool for generating a rough 2.5D or relief-style base mesh from badge, medal, award, crest, plaque and similar relief object images.

The output is not intended to be a final production-ready replica. The output is a Blender-friendly rough base model that should complete roughly 60% to 80% of the repetitive setup work: outline, base thickness, side structure, coarse relief layers and exportable objects.

The tool must support these input states:

- Front image only.
- Front and back images.
- A back image added later to an existing project.
- Uneven image quality between front and back.
- Reference images that are similar objects but not guaranteed to be the same physical piece.

The tool must not infer missing real side geometry. When there is no side image, the side should be generated parametrically.

## Part 2: MVP boundary

The first MVP should do:

- Create, save and open a project file.
- Import front, back and reference images.
- Store project metadata and assets locally.
- Run basic image preprocessing and mask cleanup.
- Generate a rough single-side relief from a front image.
- Keep a placeholder back when only the front exists.
- Add base thickness and simple side closure.
- Export OBJ and STL.
- Preserve enough project state to add a back image later.

The first MVP should not do:

- Cloud AI.
- Online inference.
- Full automatic final replica generation.
- Advanced material simulation.
- Real side reconstruction.
- Factory process optimization.
- Universal image-to-3D.
- Complex sculpting inside this app.

## Part 3: Technology choice

Recommended stack for MVP:

- Python for fastest local MVP iteration.
- PySide6 for Windows desktop UI.
- Pillow and NumPy for light image processing.
- OpenCV can be added later for stronger contour and perspective operations.
- Custom mesh generation first, then trimesh or pymeshlab later for stronger mesh repair.
- OBJ and ASCII STL first because they are easy to inspect and Blender-friendly.

This stack is appropriate because the current product is a practical local preprocessor for Blender, not a real-time sculpting engine or heavy AI research project.

## Part 4: System architecture and modules

Core modules:

- project_model: project data structures.
- project_io: create, save, load and import project assets.
- image_preprocess: image loading and basic normalization.
- mask_generator: foreground mask generation.
- mask_processing: mask cleanup, crop and grid size control.
- heightmap_generator: grayscale and layered heightmap generation.
- masked_solid_builder: rough relief solid generation from a mask footprint.
- mesh_optimize: vertex cleanup and degenerate face removal.
- manufacturability_check: advisory size and warning report.
- mesh_exporter: OBJ and STL export.
- ui: desktop shell and later editing panels.

Application flow:

```text
Project
  -> Import front/back/reference images
  -> Save project state
  -> Preprocess selected face
  -> Mask cleanup
  -> Heightmap generation
  -> Relief mesh build
  -> Mesh optimization
  -> Report
  -> Export OBJ/STL
  -> Reopen later and add back image
```

## Part 5: Project file and data structure

Project storage should use one project file plus a local resource folder:

```text
sample.medalproj
sample_assets/
  images/
  previews/
  exports/
```

The `.medalproj` file is JSON. It stores:

- Project name.
- Version.
- Front image record.
- Back image record.
- Reference image records.
- Whether front and back are the same physical object.
- Outline data.
- Dimensions.
- Edge parameters.
- Front relief parameters.
- Back relief parameters.
- Manual correction markers.
- Export history.

Image records include role, path, whether it is a reference image, quality label and preprocessing metadata.

This allows a front-only project to be created first, then reopened later and updated with a back image without rebuilding the whole project from scratch.

## Part 6: Development plan

### Phase 1: Project-based single front MVP

- Add project model.
- Add save/open project file.
- Add front image import.
- Generate rough front relief.
- Export OBJ/STL.
- Save export history.

### Phase 2: Better mask and outline controls

- Add manual foreground hints.
- Add contour preview.
- Add common outline templates: circle, ellipse, shield, polygon.
- Add simple perspective correction.

### Phase 3: Desktop UI shell

- New/open/save project.
- Import front/back/reference image.
- Parameter panel.
- Preview panel.
- Generate and export actions.

### Phase 4: Back image and incremental generation

- Add back image to existing project.
- Reuse known outline, dimensions, thickness and center alignment.
- Generate back relief into the same project.

### Phase 5: Blender-friendly split export

- Export separate objects for base, rim, front relief, front text, back relief and back text when available.
- Keep combined export as a simple fallback.

### Phase 6: Higher quality modes

- Low precision preview mode.
- Standard mode.
- High precision export mode.
- Better contour smoothing and mesh repair.

## Part 7: First code skeleton

The first code skeleton should contain:

```text
badge_relief_maker/app/core/project_model.py
badge_relief_maker/app/core/project_io.py
badge_relief_maker/app/ui/main_window.py
```

The first runnable project features are:

- Create a MedalProject object.
- Save it as `.medalproj` JSON.
- Load it later.
- Import image assets into a sibling asset folder.
- Keep front/back/reference images separate.
- Keep export history inside the project.

The existing single-side relief pipeline remains the first mesh generation path. The project layer is added above it so later front/back incremental workflows do not require users to start over.
