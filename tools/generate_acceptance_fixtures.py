"""Generate deterministic local images used by the v1 acceptance contract.

The repository keeps the generator as the source of truth so PNG/JPG fixtures can
be recreated without downloading assets or introducing opaque binary provenance.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw


FIXTURE_SIZE = (256, 192)


def _transparent_canvas():
    return Image.new("RGBA", FIXTURE_SIZE, (0, 0, 0, 0))


def _save_transparent_rectangle(directory):
    image = _transparent_canvas()
    ImageDraw.Draw(image).rectangle((40, 30, 215, 160), fill=(150, 150, 150, 255))
    image.save(directory / "transparent_rectangle.png")


def _save_transparent_circle(directory):
    image = _transparent_canvas()
    ImageDraw.Draw(image).ellipse((48, 16, 208, 176), fill=(180, 180, 180, 255))
    image.save(directory / "transparent_circle.png")


def _save_ring(directory):
    image = _transparent_canvas()
    draw = ImageDraw.Draw(image)
    draw.ellipse((48, 16, 208, 176), fill=(200, 200, 200, 255))
    draw.ellipse((88, 56, 168, 136), fill=(0, 0, 0, 0))
    image.save(directory / "transparent_ring.png")


def _save_controlled_jpgs(directory):
    dark = Image.new("RGB", FIXTURE_SIZE, (0, 0, 0))
    ImageDraw.Draw(dark).ellipse((48, 16, 208, 176), fill=(255, 255, 255))
    dark.save(directory / "black_background_white_object.jpg", quality=95, subsampling=0)

    light = Image.new("RGB", FIXTURE_SIZE, (255, 255, 255))
    ImageDraw.Draw(light).ellipse((48, 16, 208, 176), fill=(0, 0, 0))
    light.save(directory / "white_background_black_object.jpg", quality=95, subsampling=0)


def _save_gradient(directory):
    image = _transparent_canvas()
    pixels = image.load()
    for y in range(32, 160):
        for x in range(32, 224):
            value = int(round((x - 32) / 191.0 * 255.0))
            pixels[x, y] = (value, value, value, 255)
    image.save(directory / "masked_gradient.png")


def _save_asymmetric_pair(directory):
    front = _transparent_canvas()
    draw = ImageDraw.Draw(front)
    draw.ellipse((40, 12, 216, 180), fill=(120, 120, 120, 255))
    draw.polygon([(72, 96), (124, 45), (124, 147)], fill=(245, 245, 245, 255))
    front.save(directory / "asymmetric_front.png")

    back = _transparent_canvas()
    draw = ImageDraw.Draw(back)
    draw.ellipse((40, 12, 216, 180), fill=(120, 120, 120, 255))
    draw.rectangle((132, 54, 190, 138), fill=(235, 235, 235, 255))
    back.save(directory / "asymmetric_back.png")


def generate_acceptance_fixtures(output_directory):
    """Write all deterministic fixtures and return the generated manifest."""
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    _save_transparent_rectangle(directory)
    _save_transparent_circle(directory)
    _save_ring(directory)
    _save_controlled_jpgs(directory)
    _save_gradient(directory)
    _save_asymmetric_pair(directory)

    manifest = {
        "generator": "tools/generate_acceptance_fixtures.py",
        "size_px": list(FIXTURE_SIZE),
        "fixtures": {
            "transparent_rectangle.png": {"mask_mode": "alpha", "purpose": "rectangular closure and dimensions"},
            "transparent_circle.png": {"mask_mode": "alpha", "purpose": "curved footprint approximation"},
            "transparent_ring.png": {"mask_mode": "alpha", "purpose": "hole preservation and inner wall closure"},
            "black_background_white_object.jpg": {"mask_mode": "luminance-light", "purpose": "opaque light-on-dark mask"},
            "white_background_black_object.jpg": {"mask_mode": "luminance-dark", "purpose": "opaque dark-on-light mask"},
            "masked_gradient.png": {"mask_mode": "alpha", "purpose": "foreground-only height normalization and invert"},
            "asymmetric_front.png": {"mask_mode": "alpha", "purpose": "front/back orientation and alignment"},
            "asymmetric_back.png": {"mask_mode": "alpha", "purpose": "viewed-back flip and fused alignment"},
        },
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate Badge Relief Maker acceptance images.")
    parser.add_argument("output_directory", nargs="?", default="acceptance_fixtures")
    args = parser.parse_args()
    manifest = generate_acceptance_fixtures(args.output_directory)
    print(f"Generated {len(manifest['fixtures'])} fixtures in {Path(args.output_directory).resolve()}")


if __name__ == "__main__":
    main()
