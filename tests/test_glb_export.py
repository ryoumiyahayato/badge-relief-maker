import json
import struct

import numpy as np
import pytest
from PIL import Image

from badge_relief_maker.app.core.mesh_exporter import export_glb, export_glb_objects, export_mesh, implemented_formats
from badge_relief_maker.app.core.project_build import build_double_side_placeholder_from_project_file, build_front_relief_from_project_file
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
    assert primitive["material"] == 0
    assert document["accessors"][0]["count"] == 3
    assert document["accessors"][1]["count"] == 3
    assert document["accessors"][1]["type"] == "VEC3"
    assert document["accessors"][2]["count"] == 3
    assert document["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"] == [0.8, 0.8, 0.8, 1.0]
    assert len(document["bufferViews"]) == 3
    assert binary_length > 0


def test_export_glb_objects_writes_named_nodes_meshes_and_materials(tmp_path):
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)
    output = tmp_path / "split.glb"

    export_glb_objects(
        output,
        [
            {"name": "front relief", "vertices": vertices, "faces": faces, "base_color": [0.9, 0.8, 0.6, 1.0]},
            {"name": "back relief", "vertices": vertices + np.asarray([0, 0, -1]), "faces": faces, "base_color": "8080ffff"},
        ],
    )
    document, binary_length = _read_glb(output)

    assert [node["name"] for node in document["nodes"]] == ["front_relief", "back_relief"]
    assert [mesh["name"] for mesh in document["meshes"]] == ["front_relief", "back_relief"]
    assert document["scenes"][0]["nodes"] == [0, 1]
    assert document["meshes"][0]["primitives"][0]["material"] == 0
    assert document["meshes"][1]["primitives"][0]["material"] == 1
    assert len(document["materials"]) == 2
    assert document["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"] == [0.9, 0.8, 0.6, 1.0]
    assert document["materials"][1]["pbrMetallicRoughness"]["baseColorFactor"] == [128 / 255.0, 128 / 255.0, 1.0, 1.0]
    assert len(document["meshes"]) == 2
    assert len(document["bufferViews"]) == 6
    assert len(document["accessors"]) == 6
    assert binary_length > 0


def test_export_glb_materials_handle_invalid_values(tmp_path):
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)
    output = tmp_path / "invalid-material.glb"

    export_glb_objects(
        output,
        [
            {
                "name": "bad material",
                "vertices": vertices,
                "faces": faces,
                "base_color": "not-a-color",
                "metallic": "bad",
                "roughness": 2.0,
            }
        ],
    )
    document, _ = _read_glb(output)
    pbr = document["materials"][0]["pbrMetallicRoughness"]

    assert pbr["baseColorFactor"] == [0.8, 0.8, 0.8, 1.0]
    assert pbr["metallicFactor"] == 0.0
    assert pbr["roughnessFactor"] == 1.0


def test_export_glb_rejects_malformed_vertex_array(tmp_path):
    output = tmp_path / "bad-vertices.glb"

    with pytest.raises(ValueError, match="vertices must be an Nx3 array"):
        export_glb(output, [0, 0, 0], [[0, 1, 2]])


def test_export_glb_rejects_malformed_face_array(tmp_path):
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    output = tmp_path / "bad-faces.glb"

    with pytest.raises(ValueError, match="faces must be an Nx3 array"):
        export_glb(output, vertices, [[0, 1, 2, 0]])


def test_export_glb_rejects_non_finite_vertices(tmp_path):
    vertices = np.asarray([[0, 0, 0], [np.nan, 0, 0], [0, 1, 0]], dtype=float)
    output = tmp_path / "nan-vertices.glb"

    with pytest.raises(ValueError, match="vertices contain non-finite coordinates"):
        export_glb(output, vertices, [[0, 1, 2]])


def test_export_glb_rejects_invalid_face_indices(tmp_path):
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    output = tmp_path / "bad-index.glb"

    with pytest.raises(ValueError, match="faces contain vertex indices outside the vertex array"):
        export_glb(output, vertices, [[0, 1, 99]])


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


def test_project_double_placeholder_glb_preserves_split_nodes(tmp_path):
    front_path = tmp_path / "front.png"
    back_path = tmp_path / "back.png"
    Image.new("RGBA", (6, 6), (255, 255, 255, 255)).save(front_path)
    Image.new("RGBA", (6, 6), (128, 128, 128, 255)).save(back_path)

    project = create_project("GLB Double Project")
    project_path = tmp_path / "glb_double_project.medalproj"
    save_project(project, project_path)
    import_image_asset(project, project_path, front_path, "front")
    import_image_asset(project, project_path, back_path, "back")
    save_project(project, project_path)

    result = build_double_side_placeholder_from_project_file(project_path, export_format="glb", quality_mode="preview")
    document, _ = _read_glb(result.output_path)

    assert result.output_path.endswith(".glb")
    assert result.report["export_format"] == "glb"
    assert result.report["split_objects"] == ["front_relief", "back_relief"]
    assert [node["name"] for node in document["nodes"]] == ["front_relief", "back_relief"]
    assert len(document["materials"]) == 2
