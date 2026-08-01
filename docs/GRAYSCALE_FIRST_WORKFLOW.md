# Deterministic grayscale relief workflow

## Scope

The production workflow has one purpose: create and approve a binary material mask and continuous grayscale height master, then generate a closed 2.5D mesh from those two artifacts.

The source image is reference data. It can help draft a background mask and initial brightness mapping, but it is never a mesh-stage input after approval.

## Canonical meanings

### `solid_mask`

```text
True / white  = material exists
False / black = no material
```

It controls silhouette, holes and disconnected components. It never controls height.

### `height_master`

```text
0.0 = lowest solid surface
1.0 = highest solid surface
```

Only values under `solid_mask=True` are meaningful. Outside values are fixed to zero and excluded from normalization and mesh construction.

### Confirmation state

The project persists:

```text
solid_mask_confirmed
height_master_confirmed
```

Anything saved before both are true is labelled `review_required`.

## Fixed three-stage order

### 1. Confirm material area

Choose one:

1. Whole plate.
2. Automatic background draft: alpha, sampled background, border-connected colour or explicit bright/dark connected background.
3. Custom mask with ordered add/remove/fill/delete-component/rectangle/polygon edits.

Automatic removal is never final until the user confirms it. Confirmed material is locked; height generation cannot refill or delete it.

### 2. Confirm height inside material

Choose one:

1. Bright is high.
2. Dark is high.
3. Dark/light line engraving at a fixed millimetre depth.
4. Dark/light line embossing at a fixed millimetre height.
5. Fixed height.

The program may not silently choose among these meanings.

For continuous brightness modes, finite solid pixels use percentile normalization:

```text
low default  = 2%
high default = 98%
```

The interval is clipped and mapped to 0–1. The user can change black point, white point, midtone and inversion. Empty masks, non-finite values and invalid ranges are rejected. A uniform solid region receives a deterministic midpoint draft rather than division by zero.

Line modes start from a flat surface. Detected line coverage changes height by a fixed millimetre amount, is clipped to 0–1, stays inside the mask and records clipped pixels. It does not stretch black and white across the entire relief range.

Manual height operation order is fixed:

```text
automatic draft
→ global levels
→ line relief
→ region fixed height
→ local set/raise/lower/smooth edits
→ final confirmation
```

### 3. Build and export

The mesh builder reads only approved mask, approved height, dimensions and sampling settings. It uses the regular shared-vertex builder by default and creates top, bottom, outer walls, hole walls and closed components.

```text
top_z_mm = height_master × relief_height_mm
bottom_z_mm = -base_thickness_mm
```

Mask and height are resampled separately:

- mask: nearest-neighbour binary resampling;
- height: bicubic continuous resampling, clipped to 0–1, then zeroed outside the resampled mask.

Approved files must already have the same shape. The strict builder rejects misalignment instead of silently resizing one approved artifact to the other.

## Formal artifacts

```text
source_aligned.png
solid_mask.png
height_master_16bit.png
height_master_32bit.tiff
height_master_preview.png
mesh_preview.png
project.json
output.obj / output.stl / output.glb
build_report.json
```

The 8-bit preview is not a formal mesh input. The strict CLI accepts 16-bit unsigned or 32-bit float single-channel masters and records input hashes.

## Report requirements

The build report includes:

- actual X/Y grid spacing in millimetres;
- source physical pixel size;
- array and foreground grid dimensions;
- vertices and triangles;
- downsampling and interpolation policy;
- minimum-feature three-sample advice;
- estimated mesh-array memory;
- dimensions and error;
- topology, zero-area and component orientation checks;
- input and output SHA-256 hashes;
- deterministic mesh digest;
- explicit confirmation that source inference, semantic inference, automatic line interpretation and adaptive meshing were not used.

## Photo warning

A photograph contains illumination and material effects. Brightness mapping from a photograph is a draft, not recovered true geometry. The GUI, project and report must state this and require manual correction.

## Advanced isolation

Semantic regions, uncertainty previews, Bezier contours, adaptive grids and double-sided fusion may remain available under an explicit advanced entry. They are not dependencies of the simple path, cannot edit an approved master in the background and cannot prevent regular-grid export when unavailable. SciPy is optional for the basic path.

## External acceptance

Automated checks do not certify manufacturability. Review OBJ/STL/GLB in Blender and the intended slicer or CAM application, then perform a physical test where required.
