"""Application entry point."""

from __future__ import annotations

import argparse
import sys

from badge_relief_maker import __version__

from .core.approved_heightmap_builder import build_relief_from_approved_heightmap
from .core.quality_modes import quality_preset
from .core.relief_parameters import ReliefParameters


_MASK_CHOICES = ["auto", "alpha", "luminance", "luminance-dark", "luminance-light"]
_QUALITY_CHOICES = ["draft", "standard", "fine", "preview", "high"]


def run_gui(*, smoke_seconds: float | None = None) -> int:
    """Run the deterministic three-stage grayscale relief desktop application."""
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except Exception:
        print("PySide6 is not installed. Install GUI dependencies before using --gui.")
        return 2

    from .ui.deterministic_studio import MainWindow
    from .ui.qt_text import install_readable_ui_font

    app = QApplication.instance() or QApplication(sys.argv[:1])
    install_readable_ui_font(app)
    window = MainWindow()
    window.show()
    if smoke_seconds is not None:
        delay_ms = max(1, int(float(smoke_seconds) * 1000.0))
        QTimer.singleShot(delay_ms, window.close)
        QTimer.singleShot(delay_ms + 50, app.quit)
    return int(app.exec())


def _selected_action_count(args):
    import_requested = bool(args.import_front_path or args.import_back_path or args.import_reference_path)
    build_requested = bool(args.build_front or args.build_back or args.build_side or args.build_double_placeholder or args.build_double)
    heightmap_requested = bool(args.export_front_heightmap or args.export_back_heightmap or args.export_heightmap_side)
    approved_requested = bool(args.approved_heightmap_path or args.approved_solid_mask_path)
    direct_requested = bool(args.input_path or (args.output_path and not approved_requested))
    return sum(
        bool(value)
        for value in [
            args.gui or args.gui_smoke_seconds is not None,
            args.new_project_name,
            import_requested,
            build_requested,
            heightmap_requested,
            approved_requested,
            direct_requested,
        ]
    )


def _mesh_parameters(args, *, max_grid_cells):
    return ReliefParameters(
        width_mm=args.width_mm,
        height_mm=args.height_mm,
        base_thickness_mm=args.base_mm,
        relief_height_mm=args.relief_mm,
        minimum_thickness_mm=args.minimum_thickness_mm,
        max_grid_cells=max_grid_cells,
        contour_smoothing_iterations=args.contour_smoothing_iterations,
        edge_style=args.edge_style,
        bevel_mm=args.bevel_mm,
        radius_mm=args.radius_mm,
        process_profile=args.process_profile,
    )


def _execute(args):
    if args.gui or args.gui_smoke_seconds is not None:
        return run_gui(smoke_seconds=args.gui_smoke_seconds)

    if args.new_project_name:
        from .core.project_io import create_project, save_project

        if not args.project_path:
            raise ValueError("provide --project-path when using --new-project")
        project = create_project(args.new_project_name)
        path = save_project(project, args.project_path)
        print(f"Created project: {path}")
        return 0

    if args.import_front_path or args.import_back_path or args.import_reference_path:
        from .core.project_io import import_image_asset, load_project, save_project

        if not args.project_path:
            raise ValueError("provide --project-path when importing project images")
        project = load_project(args.project_path)
        if args.import_front_path:
            record = import_image_asset(project, args.project_path, args.import_front_path, "front")
            message = f"Imported front image: {record.path}"
        elif args.import_back_path:
            record = import_image_asset(project, args.project_path, args.import_back_path, "back")
            message = f"Imported back image: {record.path}"
        else:
            record = import_image_asset(
                project,
                args.project_path,
                args.import_reference_path,
                args.reference_role,
                is_reference=True,
            )
            message = f"Imported reference image: {record.path}"
        save_project(project, args.project_path)
        print(message)
        return 0

    heightmap_side = args.export_heightmap_side
    if args.export_front_heightmap:
        heightmap_side = "front"
    elif args.export_back_heightmap:
        heightmap_side = "back"
    if heightmap_side:
        from .core.project_build import export_side_heightmap_master_from_project_file

        if not args.project_path:
            raise ValueError("provide --project-path when exporting a grayscale height master")
        result = export_side_heightmap_master_from_project_file(
            args.project_path,
            side_name=heightmap_side,
            long_edge_px=args.heightmap_long_edge_px,
            output_dir=args.heightmap_output_dir,
            quality_mode="fine",
        )
        print(result.report)
        return 0

    if args.approved_heightmap_path or args.approved_solid_mask_path:
        if not args.approved_heightmap_path or not args.approved_solid_mask_path:
            raise ValueError("approved builds require both --approved-heightmap and --approved-solid-mask")
        if not args.output_path:
            raise ValueError("provide --output when building from approved artifacts")
        preset = quality_preset(args.quality)
        max_grid_cells = args.max_grid_cells if args.max_grid_cells is not None else preset["max_grid_cells"]
        params = _mesh_parameters(args, max_grid_cells=max_grid_cells)
        result = build_relief_from_approved_heightmap(
            args.approved_heightmap_path,
            args.output_path,
            mask_path=args.approved_solid_mask_path,
            parameters=params,
            quality_mode=preset["canonical_quality_mode"],
            min_feature_mm=args.min_feature_mm,
            report_path=args.build_report_path,
            allow_8bit_preview=args.allow_8bit_approved_preview,
        )
        print(result.report)
        return 0

    if args.build_double_placeholder:
        from .core.project_build import build_double_side_placeholder_from_project_file

        if not args.project_path:
            raise ValueError("provide --project-path when building a double-side placeholder")
        result = build_double_side_placeholder_from_project_file(
            args.project_path,
            export_format=args.project_export_format,
            quality_mode=args.quality,
        )
        print(result.report)
        return 0

    if args.build_double:
        from .core.project_build import build_fused_double_side_from_project_file

        if not args.project_path:
            raise ValueError("provide --project-path when building a fused double-side model")
        result = build_fused_double_side_from_project_file(
            args.project_path,
            export_format=args.project_export_format,
            quality_mode=args.quality,
        )
        print(result.report)
        return 0

    requested_side = args.build_side
    if args.build_front:
        requested_side = "front"
    elif args.build_back:
        requested_side = "back"

    if requested_side:
        from .core.project_build import build_side_relief_from_project_file

        if not args.project_path:
            raise ValueError("provide --project-path when building from a project")
        result = build_side_relief_from_project_file(
            args.project_path,
            side_name=requested_side,
            export_format=args.project_export_format,
            quality_mode=args.quality,
        )
        print(result.report)
        return 0

    if not args.input_path and not args.output_path:
        print("Badge Relief Maker is ready. Use --gui, or provide approved mask and height artifacts.")
        return 0

    from .core.single_side_pipeline import build_single_side_relief

    preset = quality_preset(args.quality)
    max_grid_cells = args.max_grid_cells if args.max_grid_cells is not None else preset["max_grid_cells"]
    params = ReliefParameters(
        width_mm=args.width_mm,
        height_mm=args.height_mm,
        base_thickness_mm=args.base_mm,
        relief_height_mm=args.relief_mm,
        invert_height=args.invert,
        mask_mode=args.mask_mode,
        alpha_threshold=args.alpha_threshold,
        luminance_threshold=args.luminance_threshold,
        minimum_thickness_mm=args.minimum_thickness_mm,
        use_mask_footprint=not args.rectangle_footprint,
        crop_to_foreground=not args.no_crop,
        crop_padding_px=args.crop_padding_px,
        max_grid_cells=max_grid_cells,
        min_component_pixels=args.min_component_pixels,
        fill_hole_pixels=args.fill_hole_pixels,
        mask_smooth_iterations=args.mask_smooth_iterations,
        contour_smoothing_iterations=args.contour_smoothing_iterations,
        rim_width_px=args.rim_width_px,
        rim_width_mm=args.rim_width_mm,
        rim_height_mm=args.rim_height_mm,
        rim_profile=args.rim_profile,
        edge_style=args.edge_style,
        bevel_mm=args.bevel_mm,
        radius_mm=args.radius_mm,
        height_mode=args.height_mode,
        background_depth_mm=args.background_depth_mm,
        uniform_height_normalized=args.uniform_height,
        smooth_strength=args.smooth_strength,
        detail_sharpness=args.detail_sharpness,
        process_profile=args.process_profile,
        manual_crop_box=tuple(args.manual_crop_box) if args.manual_crop_box else None,
    )
    result = build_single_side_relief(args.input_path, args.output_path, params, preview_dir=args.preview_dir)
    print(result.report)
    return 0


def main(argv=None) -> int:
    """Run the CLI with an explicit argument sequence for testability."""
    if argv is None:
        argv = []

    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic 2.5D relief from an approved binary solid mask and approved 16/32-bit height master. "
            "Source-image interpretation remains a separate draft workflow."
        )
    )
    parser.add_argument("--version", action="version", version=f"Badge Relief Maker {__version__}")
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--gui-smoke-seconds", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--new-project", dest="new_project_name")
    parser.add_argument("--project-path", dest="project_path")

    import_group = parser.add_mutually_exclusive_group()
    import_group.add_argument("--import-front", dest="import_front_path")
    import_group.add_argument("--import-back", dest="import_back_path")
    import_group.add_argument("--import-reference", dest="import_reference_path")
    parser.add_argument("--reference-role", default="reference")

    build_group = parser.add_mutually_exclusive_group()
    build_group.add_argument("--build-front", action="store_true")
    build_group.add_argument("--build-back", action="store_true")
    build_group.add_argument("--build-side", choices=["front", "back"])
    build_group.add_argument("--build-double-placeholder", action="store_true")
    build_group.add_argument("--build-double", action="store_true", help="advanced: build one aligned fused front/back solid")

    heightmap_group = parser.add_mutually_exclusive_group()
    heightmap_group.add_argument("--export-front-heightmap", action="store_true")
    heightmap_group.add_argument("--export-back-heightmap", action="store_true")
    heightmap_group.add_argument("--export-heightmap-side", choices=["front", "back"])
    parser.add_argument("--heightmap-long-edge-px", type=int, default=8192)
    parser.add_argument("--heightmap-output-dir")

    parser.add_argument("--approved-heightmap", dest="approved_heightmap_path", help="approved 16-bit PNG or 32-bit float TIFF")
    parser.add_argument("--approved-solid-mask", dest="approved_solid_mask_path", help="approved aligned binary material mask")
    parser.add_argument("--build-report", dest="build_report_path", help="optional build_report.json path")
    parser.add_argument("--allow-8bit-approved-preview", action="store_true", help=argparse.SUPPRESS)

    parser.add_argument("--project-export-format", default="obj", choices=["obj", "stl", "glb"])
    parser.add_argument("--quality", default="standard", choices=_QUALITY_CHOICES)
    parser.add_argument("--input", dest="input_path", help="legacy source-image draft build; not the approved production path")
    parser.add_argument("--output", dest="output_path")
    parser.add_argument("--width-mm", type=float, default=80.0)
    parser.add_argument("--height-mm", type=float, default=80.0)
    parser.add_argument("--base-mm", type=float, default=2.0)
    parser.add_argument("--relief-mm", type=float, default=3.0)
    parser.add_argument("--min-feature-mm", type=float, default=None)
    parser.add_argument("--minimum-thickness-mm", type=float, default=0.8)
    parser.add_argument("--invert", action="store_true")
    parser.add_argument("--mask-mode", default="auto", choices=_MASK_CHOICES)
    parser.add_argument("--alpha-threshold", type=int, default=1)
    parser.add_argument("--luminance-threshold", type=float, default=20.0)
    parser.add_argument("--rectangle-footprint", action="store_true")
    parser.add_argument("--contour-smoothing-iterations", type=int, default=1)
    parser.add_argument("--rim-width-px", type=int, default=0)
    parser.add_argument("--rim-width-mm", type=float, default=0.0)
    parser.add_argument("--rim-height-mm", type=float, default=0.0)
    parser.add_argument("--rim-profile", default="flat", choices=["flat", "linear", "smooth"])
    parser.add_argument("--edge-style", default="straight", choices=["straight", "sloped", "bevel", "rounded"])
    parser.add_argument("--bevel-mm", type=float, default=0.0)
    parser.add_argument("--radius-mm", type=float, default=0.0)
    parser.add_argument("--height-mode", default="emboss", choices=["emboss", "flat", "grayscale", "layers", "hybrid"])
    parser.add_argument("--background-depth-mm", type=float, default=0.0)
    parser.add_argument("--uniform-height", type=float, default=1.0)
    parser.add_argument("--smooth-strength", type=float, default=0.0)
    parser.add_argument("--detail-sharpness", type=float, default=0.0)
    parser.add_argument("--process-profile", default="general", choices=["general", "fdm", "resin", "cnc", "mould"])
    parser.add_argument("--manual-crop-box", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    parser.add_argument("--no-crop", action="store_true")
    parser.add_argument("--crop-padding-px", type=int, default=1)
    parser.add_argument("--max-grid-cells", type=int, default=None)
    parser.add_argument("--min-component-pixels", type=int, default=1)
    parser.add_argument("--fill-hole-pixels", type=int, default=0)
    parser.add_argument("--mask-smooth-iterations", type=int, default=0)
    parser.add_argument("--preview-dir", dest="preview_dir")
    args = parser.parse_args(argv)

    if _selected_action_count(args) > 1:
        parser.error(
            "choose exactly one primary action: GUI, new project, import, grayscale export, approved-artifact build, project build, or legacy direct build"
        )
    if (args.approved_heightmap_path or args.approved_solid_mask_path) and args.input_path:
        parser.error("choose approved artifacts or --input, not both")
    if not (args.approved_heightmap_path or args.approved_solid_mask_path) and bool(args.input_path) != bool(args.output_path):
        parser.error("legacy direct image builds require both --input and --output")

    try:
        return _execute(args)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def cli() -> int:
    """Console-script wrapper that consumes the real process arguments."""
    return main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(cli())
