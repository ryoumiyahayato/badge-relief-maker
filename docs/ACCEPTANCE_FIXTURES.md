# Acceptance Fixtures and Validation Assets

The v1 acceptance images are generated locally from source code rather than downloaded or stored as opaque binaries.

```powershell
python tools/generate_acceptance_fixtures.py acceptance_fixtures
```

The command creates:

- `transparent_rectangle.png` — rectangular closure and physical dimensions;
- `transparent_circle.png` — curved footprint approximation;
- `transparent_ring.png` — hole preservation and inner-wall closure;
- `black_background_white_object.jpg` — controlled light-on-dark luminance mask;
- `white_background_black_object.jpg` — controlled dark-on-light luminance mask;
- `masked_gradient.png` — foreground-only normalization and invert behavior;
- `asymmetric_front.png` and `asymmetric_back.png` — viewed-back flip, alignment and fused-body checks;
- `manifest.json` — expected mask modes and fixture purposes.

Generate mesh artifacts and independent trimesh read-back reports with:

```powershell
python tools/generate_validation_assets.py validation_assets --max-grid-cells 5000
```

This creates:

- single-circle OBJ, STL and GLB files at 80 × 60 mm;
- a ring OBJ used to verify retained holes and watertight inner walls;
- aligned fused-double OBJ, STL and GLB files using asymmetric front/back artwork;
- `validation_manifest.json` containing core reports, expected dimensions and independent reload facts.

The manifest deliberately leaves Blender, slicer, CAM and physical-sample fields as `pending`. Programmatic trimesh reload is useful regression evidence but does not replace those external checks.

Generation is deterministic for the same source revision and dependency behavior. Record the tested commit, Python, Pillow and trimesh versions plus generated-file hashes in `docs/VALIDATION_RECORD.md` when the Windows or external acceptance gate is performed.
