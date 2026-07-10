import json

from PIL import Image

from tools.generate_acceptance_fixtures import FIXTURE_SIZE, generate_acceptance_fixtures


def test_acceptance_fixture_generator_writes_required_images_and_manifest(tmp_path):
    manifest = generate_acceptance_fixtures(tmp_path)

    expected = set(manifest["fixtures"])
    assert expected == {
        "transparent_rectangle.png",
        "transparent_circle.png",
        "transparent_ring.png",
        "black_background_white_object.jpg",
        "white_background_black_object.jpg",
        "masked_gradient.png",
        "asymmetric_front.png",
        "asymmetric_back.png",
    }
    for filename in expected:
        path = tmp_path / filename
        assert path.is_file()
        with Image.open(path) as image:
            assert image.size == FIXTURE_SIZE

    stored = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert stored == manifest
    assert stored["fixtures"]["transparent_ring.png"]["purpose"].startswith("hole preservation")


def test_generated_ring_keeps_a_transparent_center(tmp_path):
    generate_acceptance_fixtures(tmp_path)

    with Image.open(tmp_path / "transparent_ring.png").convert("RGBA") as image:
        assert image.getpixel((128, 96))[3] == 0
        assert image.getpixel((128, 20))[3] == 255
