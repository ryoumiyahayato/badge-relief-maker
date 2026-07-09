"""Mesh export helpers."""

import json
import struct
from pathlib import Path

import numpy as np


_DEFAULT_BASE_COLOR = [0.8, 0.8, 0.8, 1.0]


def _safe_obj_name(name):
    text = str(name or "object").strip()
    text = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)
    return text or "object"


def export_obj(path, vertices, faces):
    """Export a minimal OBJ file."""
    path = Path(path)
    with path.open("w", encoding="utf-8") as fh:
        for x, y, z in vertices:
            fh.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            fh.write(f"f {a + 1} {b + 1} {c + 1}\n")


def export_obj_objects(path, objects):
    """Export multiple named mesh objects to one OBJ file.

    Each object item should contain name, vertices and faces. Blender imports
    OBJ object markers as separate editable objects or mesh groups depending on
    import settings, which is useful for the rough-base workflow.
    """
    path = Path(path)
    vertex_offset = 0
    with path.open("w", encoding="utf-8") as fh:
        for item in objects:
            name = _safe_obj_name(item["name"])
            vertices = np.asarray(item["vertices"], dtype=float)
            faces = np.asarray(item["faces"], dtype=np.int64)
            fh.write(f"o {name}\n")
            for x, y, z in vertices:
                fh.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
            for a, b, c in faces:
                fh.write(f"f {a + 1 + vertex_offset} {b + 1 + vertex_offset} {c + 1 + vertex_offset}\n")
            vertex_offset += len(vertices)


def _facet_normal(a, b, c):
    """Compute a normalized triangle normal."""
    ab = b - a
    ac = c - a
    normal = np.cross(ab, ac)
    length = float(np.linalg.norm(normal))
    if length == 0.0:
        return np.asarray([0.0, 0.0, 0.0], dtype=float)
    return normal / length


def export_ascii_stl(path, vertices, faces, solid_name="badge_relief"):
    """Export a minimal ASCII STL file.

    ASCII STL is larger than binary STL but easy to inspect and sufficient for
    the first local MVP. A binary STL exporter can be added later.
    """
    path = Path(path)
    verts = np.asarray(vertices, dtype=float)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f"solid {solid_name}\n")
        for face in faces:
            a, b, c = verts[face[0]], verts[face[1]], verts[face[2]]
            n = _facet_normal(a, b, c)
            fh.write(f"  facet normal {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")
            fh.write("    outer loop\n")
            fh.write(f"      vertex {a[0]:.6f} {a[1]:.6f} {a[2]:.6f}\n")
            fh.write(f"      vertex {b[0]:.6f} {b[1]:.6f} {b[2]:.6f}\n")
            fh.write(f"      vertex {c[0]:.6f} {c[1]:.6f} {c[2]:.6f}\n")
            fh.write("    endloop\n")
            fh.write("  endfacet\n")
        fh.write(f"endsolid {solid_name}\n")


def _vertex_normals(vertices, faces):
    """Return area-weighted per-vertex normals for GLB export."""
    vertices = np.asarray(vertices, dtype=np.float32).reshape((-1, 3))
    faces = np.asarray(faces, dtype=np.int64).reshape((-1, 3))
    normals = np.zeros_like(vertices, dtype=np.float32)
    for a, b, c in faces:
        p0 = vertices[int(a)]
        p1 = vertices[int(b)]
        p2 = vertices[int(c)]
        normal = np.cross(p1 - p0, p2 - p0)
        length = float(np.linalg.norm(normal))
        if length == 0.0:
            continue
        normals[int(a)] += normal
        normals[int(b)] += normal
        normals[int(c)] += normal

    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 0.0
    normals[valid] = normals[valid] / lengths[valid, None]
    normals[~valid] = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
    return np.ascontiguousarray(normals, dtype=np.float32)


def _append_binary_blob(binary_blob, payload):
    """Append one aligned GLB binary payload and return updated blob plus offset."""
    offset = _aligned_length(len(binary_blob))
    binary_blob = _pad_bytes(binary_blob, b"\x00") + payload
    return binary_blob, offset


def _mesh_arrays(vertices, faces):
    verts = np.asarray(vertices, dtype=np.float32).reshape((-1, 3))
    faces = np.asarray(faces, dtype=np.int64).reshape((-1, 3))
    if len(verts) > 0 and len(faces) > 0 and (faces.min() < 0 or faces.max() >= len(verts)):
        raise ValueError("faces contain vertex indices outside the vertex array")
    return verts, faces


def _base_color(item):
    raw = item.get("base_color", item.get("color", _DEFAULT_BASE_COLOR))
    if isinstance(raw, str):
        raw = raw.strip().lstrip("#")
        if len(raw) in {6, 8}:
            values = [int(raw[index : index + 2], 16) / 255.0 for index in range(0, len(raw), 2)]
            if len(values) == 3:
                values.append(1.0)
            return values
    try:
        values = [float(value) for value in raw]
    except TypeError:
        return list(_DEFAULT_BASE_COLOR)
    if len(values) == 3:
        values.append(1.0)
    if len(values) != 4:
        return list(_DEFAULT_BASE_COLOR)
    return [float(min(max(value, 0.0), 1.0)) for value in values]


def _material_from_item(item, name):
    return {
        "name": f"{name}_material",
        "pbrMetallicRoughness": {
            "baseColorFactor": _base_color(item),
            "metallicFactor": float(item.get("metallic", 0.0)),
            "roughnessFactor": float(item.get("roughness", 0.65)),
        },
    }


def export_glb(path, vertices, faces):
    """Export a minimal binary glTF 2.0 GLB mesh.

    The exporter writes positions, vertex normals, triangle indices and one basic
    material. Texture coordinates and textures are intentionally outside this
    MVP path.
    """
    export_glb_objects(path, [{"name": "badge_relief", "vertices": vertices, "faces": faces}])


def export_glb_objects(path, objects):
    """Export multiple named mesh objects to one binary glTF 2.0 GLB file.

    This preserves rough front/back object separation as separate glTF nodes and
    meshes. Each mesh receives one simple material. UVs and textures are outside
    this MVP path.
    """
    nodes = []
    meshes = []
    accessors = []
    buffer_views = []
    materials = []
    scene_node_indices = []
    binary_blob = b""

    for item in objects:
        name = _safe_obj_name(item.get("name", "object"))
        vertices, faces = _mesh_arrays(item.get("vertices", []), item.get("faces", []))
        node_index = len(nodes)
        scene_node_indices.append(node_index)
        if len(vertices) == 0 or len(faces) == 0:
            nodes.append({"name": name})
            continue

        positions = np.ascontiguousarray(vertices, dtype=np.float32)
        normals = _vertex_normals(positions, faces)
        indices = np.ascontiguousarray(faces.reshape(-1), dtype=np.uint32)

        position_bytes = positions.tobytes()
        binary_blob, position_offset = _append_binary_blob(binary_blob, position_bytes)
        position_view = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": position_offset, "byteLength": len(position_bytes), "target": 34962})

        normal_bytes = normals.tobytes()
        binary_blob, normal_offset = _append_binary_blob(binary_blob, normal_bytes)
        normal_view = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": normal_offset, "byteLength": len(normal_bytes), "target": 34962})

        index_bytes = indices.tobytes()
        binary_blob, index_offset = _append_binary_blob(binary_blob, index_bytes)
        index_view = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": index_offset, "byteLength": len(index_bytes), "target": 34963})

        mins = positions.min(axis=0).astype(float).tolist()
        maxs = positions.max(axis=0).astype(float).tolist()
        position_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": position_view,
                "byteOffset": 0,
                "componentType": 5126,
                "count": int(len(positions)),
                "type": "VEC3",
                "min": mins,
                "max": maxs,
            }
        )
        normal_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": normal_view,
                "byteOffset": 0,
                "componentType": 5126,
                "count": int(len(normals)),
                "type": "VEC3",
            }
        )
        index_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": index_view,
                "byteOffset": 0,
                "componentType": 5125,
                "count": int(indices.size),
                "type": "SCALAR",
            }
        )

        material_index = len(materials)
        materials.append(_material_from_item(item, name))
        mesh_index = len(meshes)
        meshes.append(
            {
                "name": name,
                "primitives": [
                    {
                        "attributes": {"POSITION": position_accessor, "NORMAL": normal_accessor},
                        "indices": index_accessor,
                        "mode": 4,
                        "material": material_index,
                    }
                ],
            }
        )
        nodes.append({"mesh": mesh_index, "name": name})

    binary_blob = _pad_bytes(binary_blob, b"\x00")
    document = {
        "asset": {"version": "2.0", "generator": "Badge Relief Maker"},
        "scene": 0,
        "scenes": [{"nodes": scene_node_indices}],
        "nodes": nodes,
    }
    if meshes:
        document["meshes"] = meshes
        document["materials"] = materials
        document["buffers"] = [{"byteLength": len(binary_blob)}]
        document["bufferViews"] = buffer_views
        document["accessors"] = accessors
    _write_glb(path, document, binary_blob if meshes else b"")


def _aligned_length(length):
    return (int(length) + 3) & ~3


def _pad_bytes(data, pad_byte):
    padding = _aligned_length(len(data)) - len(data)
    if padding:
        data += pad_byte * padding
    return data


def _write_glb(path, document, binary_blob=b""):
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk = _pad_bytes(json_chunk, b" ")
    chunks = [(0x4E4F534A, json_chunk)]
    if binary_blob:
        chunks.append((0x004E4942, binary_blob))
    total_length = 12 + sum(8 + len(data) for _, data in chunks)
    with Path(path).open("wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total_length))
        for chunk_type, data in chunks:
            fh.write(struct.pack("<II", len(data), chunk_type))
            fh.write(data)


def export_mesh(path, vertices, faces):
    """Export mesh by file extension."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".obj":
        export_obj(path, vertices, faces)
    elif suffix == ".stl":
        export_ascii_stl(path, vertices, faces)
    elif suffix == ".glb":
        export_glb(path, vertices, faces)
    else:
        raise ValueError(f"unsupported export format: {suffix}")


def supported_formats():
    """Return planned export formats."""
    return {"stl", "obj", "glb"}


def implemented_formats():
    """Return currently implemented export formats."""
    return {"obj", "stl", "glb"}
