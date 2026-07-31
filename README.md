# Badge Relief Maker

Badge Relief Maker is a Windows-first local tool for one narrowly defined job:

> Convert an image into a user-approved binary material mask and grayscale height master, then build a closed, dimensioned 2.5D relief mesh from those approved artifacts.

The program does **not** recover true depth from one photograph. Brightness may represent height in a designed height map, but in an ordinary photograph it also contains shadow, highlight, material colour and reflection. Photo-derived height is therefore a draft that requires manual review.

## Product model

The default workflow has three stages:

```text
Import image
→ choose the material-area mode
→ correct and confirm solid_mask
→ choose the height interpretation
→ correct and confirm height_master
→ set millimetre dimensions
→ build a regular-grid mesh
→ export
```

The two approved artifacts have separate meanings:

- `solid_mask.png`: white/true means material exists; black/false means no material. It does not encode height.
- `height_master_16bit.png` or `height_master_32bit.tiff`: values from 0 to 1 encode relative surface height only inside the material mask. Pixels outside the mask are fixed to zero and are excluded from normalization.

After both artifacts are confirmed, the mesh stage reads only:

```text
approved solid_mask
approved height_master
physical dimensions
mesh sampling settings
```

It does not return to the source image for background recognition, line interpretation, semantic classification or height replacement.

## Install and verify

Python 3.10–3.12 is supported.

```powershell
python -m pip install -e ".[dev]"
python -m ruff check badge_relief_maker tests
python -m pytest -q
python -m badge_relief_maker.app --help
python -m badge_relief_maker.app --version
```

Launch the default desktop workflow:

```powershell
python -m badge_relief_maker.app --gui
```

The default window shows four previews: original image, binary material mask, height master and shaded 3D preview. Its controls are ordered as entity confirmation, height confirmation and output. Advanced semantic, Bezier and adaptive tools remain available only through the explicit **Advanced** entry and do not modify approved artifacts in the background.

The simple approved-artifact path does not require SciPy. Install `.[advanced]` for legacy/advanced image-processing modules, or `.[package]` for the complete Windows executable.

## Stage 1: material area

The user chooses one of three modes:

- **Whole plate**: the full selected plate is material, regardless of white or black pixels.
- **Automatic background removal**: alpha is preferred, followed by user background samples, border-connected colour removal, or an explicit bright/dark background threshold. The result is only a draft.
- **Custom material area**: add/remove brush, connected fill/delete, rectangle and polygon edits, with undo/redo.

Confirming this stage locks `solid_mask`. Height processing cannot alter it.

## Stage 2: height interpretation

The user explicitly chooses:

- bright is high;
- dark is high;
- line engraving with a fixed millimetre depth;
- line embossing with a fixed millimetre height;
- one fixed height.

Continuous brightness modes use 2nd/98th percentile normalization by default, calculated only over finite solid pixels. The controls expose black point, white point, midtone, inversion and reset. The 8-bit image is display-only; formal output is 16-bit PNG or 32-bit float TIFF.

Manual height edits are applied in a fixed order:

```text
automatic draft
→ global levels
→ fixed-depth line relief
→ fixed region heights
→ local raise/lower/smooth edits
→ final confirmation
```

## Stage 3: deterministic mesh

The default production path uses a regular shared-vertex grid. It generates:

- top height surface;
- flat bottom;
- outer side walls;
- hole walls;
- closed independent components;
- consistent face orientation.

The internal coordinate convention is:

```text
top_z_mm = height_master × relief_height_mm
bottom_z_mm = -base_thickness_mm
```

The report records the actual X/Y grid spacing in millimetres, source physical pixel spacing, rows/columns, vertices, triangles, downsampling, minimum-feature advice, estimated memory, topology and input hashes. A feature intended to be retained should span about three sampling units.

Adaptive meshing remains an advanced/experimental option. It is off by default and is not the only available exporter.

## Strict approved-artifact CLI

```powershell
python -m badge_relief_maker.app `
  --approved-heightmap height_master_16bit.png `
  --approved-solid-mask solid_mask.png `
  --output result.stl `
  --width-mm 100 `
  --height-mm 80 `
  --base-mm 2 `
  --relief-mm 3 `
  --min-feature-mm 0.3 `
  --quality standard
```

This entry:

- requires both aligned approved files;
- rejects an 8-bit preview as a formal height master;
- rejects shape mismatches instead of silently resizing approved inputs;
- uses nearest-neighbour binary mask resampling and bicubic continuous-height resampling only when grid downsampling is required;
- writes `build_report.json` beside the mesh by default;
- records both input SHA-256 hashes and a deterministic mesh digest.

Supported exports are OBJ, STL and GLB. OBJ keeps named front, side-wall and flat-back groups. STL has no embedded unit metadata; the project convention is millimetres.

## Canonical project artifacts

The default workflow writes:

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

`project.json` persists confirmation state, source parameters, ordered material edits, ordered height edits, final artifact hashes and the rule that the source image is reference-only after approval. An unconfirmed export is marked `review_required` and must not be treated as a final manufacturing result.

## Windows executable

```powershell
./build_windows.ps1
```

The package job validates `--help`, `--version`, no-argument GUI startup, approved-mask/height OBJ and STL builds, generated reports, file hashes and clean process shutdown. GitHub Actions runs the complete test suite on Windows Python 3.10 and 3.12.

## Limits and external acceptance

- A real photo cannot automatically provide reliable true geometry from brightness alone.
- Low-resolution input cannot gain genuine detail merely by increasing mesh density.
- Automatic topology and manufacturability diagnostics do not replace Blender inspection, slicer/CAM validation or a physical test.
- Advanced adaptive and double-sided workflows remain separate from the default approved-mask/height path and may require additional manual acceptance.

See [`docs/GRAYSCALE_FIRST_WORKFLOW.md`](docs/GRAYSCALE_FIRST_WORKFLOW.md) for the technical contract and [`docs/中文使用说明.md`](docs/中文使用说明.md) for the shortest Chinese user procedure.
