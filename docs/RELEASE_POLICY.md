# Release policy

`badge-relief-maker` has its own semantic version and does not share CAD Photo to DXF version numbers. `pyproject.toml` is the only editable version source; package metadata, CLI, reports and Windows PE metadata derive from it.

Until Windows 3.10/3.12, clean EXE, GUI interaction, Blender, slicer, CAM and physical evidence records all exist for the same commit, GitHub releases must be marked **prerelease** and described as a manufacturing candidate. Missing physical evidence blocks any manufacturing-grade release.
