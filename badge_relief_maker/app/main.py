"""Application entry point."""

import argparse

from .core.relief_parameters import ReliefParameters
from .core.single_side_pipeline import build_single_side_relief


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build a basic badge relief OBJ from one image.")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_path")
    parser.add_argument("--width-mm", type=float, default=80.0)
    parser.add_argument("--height-mm", type=float, default=80.0)
    parser.add_argument("--base-mm", type=float, default=2.0)
    parser.add_argument("--relief-mm", type=float, default=3.0)
    parser.add_argument("--invert", action="store_true")
    parser.add_argument("--rectangle-footprint", action="store_true")
    args = parser.parse_args(argv)

    if not args.input_path or not args.output_path:
        print("Badge Relief Maker scaffold is ready. Provide --input and --output to build an OBJ.")
        return 0

    params = ReliefParameters(
        width_mm=args.width_mm,
        height_mm=args.height_mm,
        base_thickness_mm=args.base_mm,
        relief_height_mm=args.relief_mm,
        invert_height=args.invert,
        use_mask_footprint=not args.rectangle_footprint,
    )
    result = build_single_side_relief(args.input_path, args.output_path, params)
    print(result.report)
    return 0
