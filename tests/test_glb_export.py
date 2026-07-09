import json
import struct

import numpy as np
from PIL import Image

from badge_relief_maker.app.core.mesh_exporter import export_glb, export_mesh, implemented_formats
from badge_relief_maker.app.core.project_build import build_front_relief_from_project_file
from badge_relief_maker.app.core.project_io import create_project, import_image_asset, save_project


def _read_glb(path):
    data = path.read_bytes()
    magic, version, total_length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67
    assert version == 2
    assert total_length == len(data)
    json_length, json_type = struct.unpack_from("<II", data, 12)
    assert json_type == 0x4E4F534A
    json_data = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    offset = 20 + json_length
    binary_length = 0
    if offset < len(data):
        binary_length, binary_type = struct.unpack_from("<II", data, offset)
        assert binary_type == 0x004E4942
    return json_data, binary_length


def test_export_glb_writes_binary_gltf_header_and_mesh(tmp_path):
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)
    output = tmp_path / "mesh.glb"

    export_glb(output, vertices, faces)
    document, binary_length = _read_glb(output)
    primitive = document["meshes"][0]["primitives"][0]

    assert output.exists()
    assert document["asset"]["version"] == "2.0"
    assert primitive["mode"] == 4
    assert primitive["attributes"]["POSITION"] == 0
    assert primitive["attributes"]["NORMAL"] == 1
    assert primitive["indices"] == 2
    assert document["accessors"][0]["count"] == 3
    assert document["accessors"][1]["count"] == 3
    assert document["accessors"][1]["type"] == "VEC3"
    assert document["accessors"][2]["count"] == 3
    assert len(document["bufferViews"]) == 3
    assert binary_length > 0


def test_export_mesh_dispatches_glb(tmp_path):
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)
    output = tmp_path / "mesh.glb"

    export_mesh(output, vertices, faces)

    assert output.read_bytes().startswith(b"glTF")
    assert "glb" in implemented_formats()


def test_project_front_build_can_export_glb(tmp_path):
    image_path = tmp_path / "front.png"
    Image.new("RGBA", (6, 6), (255, 255, 255, 255)).save(image_path)

    project = create_project("GLB Project")
    project_path = tmp_path / "glb_project.medalproj"
    save_project(project, project_path)
    import_image_asset(project, project_path, image_path, "front")
    save_project(project, project_path)

    result = build_front_relief_from_project_file(project_path, export_format="glb", quality_mode="preview")

    assert result.output_path.endswith(".glb")
    assert result.report["export_format"] == "glb"
    assert open(result.output_path, "rb").read(4) == b"glTF"
