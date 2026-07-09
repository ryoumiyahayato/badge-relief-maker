"""Mesh export helpers."""

import json
import struct
from pathlib import Path

import numpy as np


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


def export_glb(path, vertices, faces):
    """Export a minimal binary glTF 2.0 GLB mesh.

    The exporter writes positions and triangle indices only. Materials, normals,
    texture coordinates and object splitting are intentionally outside this MVP
    path.
    """
    path = Path(path)
    verts = np.asarray(vertices, dtype=np.float32).reshape((-1, 3))
    faces = np.asarray(faces, dtype=np.int64).reshape((-1, 3))

    if len(verts) == 0 or len(faces) == 0:
        _write_glb(path, {"asset": {"version": "2.0", "generator": "Badge Relief Maker"}, "scene": 0, "scenes": [{"nodes": []}]})
        return

    if faces.min() < 0 or faces.max() >= len(verts):
        raise ValueError("faces contain vertex indices outside the vertex array")

    positions = np.ascontiguousarray(verts, dtype=np.float32)
    indices = np.ascontiguousarray(faces.reshape(-1), dtype=np.uint32)
    position_bytes = positions.tobytes()
    index_offset = _aligned_length(len(position_bytes))
    binary_blob = _pad_bytes(position_bytes, b"\x00") + indices.tobytes()
    binary_blob = _pad_bytes(binary_blob, b"\x00")

    mins = positions.min(axis=0).astype(float).tolist()
    maxs = positions.max(axis=0).astype(float).tolist()
    document = {
        "asset": {"version": "2.0", "generator": "Badge Relief Maker"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "badge_relief"}],
        "meshes": [
            {
                "name": "badge_relief",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "mode": 4,
                    }
                ],
            }
        ],
        "buffers": [{"byteLength": len(binary_blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": indices.nbytes, "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5126,
                "count": int(len(positions)),
                "type": "VEC3",
                "min": mins,
                "max": maxs,
            },
            {
                "bufferView": 1,
                "byteOffset": 0,
                "componentType": 5125,
                "count": int(indices.size),
                "type": "SCALAR",
            },
        ],
    }
    _write_glb(path, document, binary_blob)


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
