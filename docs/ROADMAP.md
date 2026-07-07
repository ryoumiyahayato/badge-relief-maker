# Roadmap

## Phase 1: Single side relief MVP

Goal: one clean front image can generate a basic exportable relief model.

Tasks:

1. Load JPG and PNG.
2. Support clean transparent PNG first.
3. Generate foreground mask.
4. Preview mask.
5. Build grayscale heightmap.
6. Build regular grid relief surface.
7. Add base thickness.
8. Add simple side walls.
9. Export OBJ.
10. Add STL export.
11. Add basic report.

Acceptance:

- A simple emblem PNG can produce an OBJ file.
- The output has visible relief height.
- User can set width, height, base thickness and relief height.

## Phase 2: Basic repair and export

Goal: make generated models easier to use in Blender and manufacturing tests.

Tasks:

1. Face count report.
2. Simple centering and scaling.
3. Duplicate vertex cleanup.
4. Normal direction check.
5. STL export.
6. GLB export.
7. Output folder management.
8. Basic warnings for tiny and thin details.

Acceptance:

- Output opens in Blender.
- Export formats are predictable.
- The report warns that manufacturing checks are advisory only.

## Phase 3: Desktop GUI

Goal: non technical user can run the pipeline.

Tasks:

1. Main window.
2. Image import panel.
3. Mask preview panel.
4. Parameter panel.
5. Generate button.
6. Export buttons.
7. Log or warning panel.
8. Open output folder.

Acceptance:

- User can import an image and export a model without using command line.

## Phase 4: Double side mode

Goal: front and back images can form one model.

Tasks:

1. Front and back import slots.
2. Separate mask and heightmap generation.
3. Center alignment.
4. Scale alignment.
5. Optional rotation adjustment.
6. Total thickness control.
7. Side wall generation.
8. Combined model export.

Acceptance:

- Two same size test images can become one two sided relief solid.

## Phase 5: Region layer editing

Goal: user can control local heights.

Tasks:

1. Connected region detection.
2. Region selection in preview.
3. Height slider per region.
4. Layer list.
5. Region smoothing and edge sharpness.
6. Save and reload settings.

Acceptance:

- User can raise letters, leaves or ornaments separately from the base.

## Phase 6: Optional AI assistance

Goal: optional quality improvement without changing the local first strategy.

Possible features:

1. Better foreground segmentation.
2. Automatic region grouping.
3. Line art cleanup.
4. Detail enhancement before heightmap generation.

Rules:

- AI must stay optional.
- Cloud must stay optional.
- The traditional pipeline must keep working without AI.
