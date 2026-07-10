# Acceptance Image Fixtures

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

Generation is deterministic for the same Pillow behavior and source revision. Record the tested commit, Python/Pillow versions and generated-file hashes in `docs/VALIDATION_RECORD.md` when the Windows, Blender, slicer or CAM gate is performed.

The generator and its tests do not themselves prove Blender, slicer, CAM or physical acceptance. They only provide reproducible inputs for those records.
