"""Mesh export helpers."""

import json
import os
import struct
import tempfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np


_DEFAULT_BASE_COLOR = [0.8, 0.8, 0.8, 1.0]


@contextmanager
def _atomic_writer(path, mode, encoding=None):
    """Write beside the target, flush to disk, then atomically replace it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary_path = Path(temporary_name)
    try:
        kwargs = {} if "b" in mode else {"encoding": encoding or "utf-8", "newline": "\n"}
        with os.fdopen(file_descriptor, mode, **kwargs) as fh:
            yield fh
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def _safe_obj_name(name):
    text = str(name or "object").strip()
    text = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)
    return text or "object"


def export_obj(path, vertices, faces):
    """Export a minimal OBJ file atomically."""
    vertices, faces = _mesh_arrays(vertices, faces)
    with _atomic_writer(path, "w", encoding="utf-8") as fh:
        for x, y, z in vertices:
            fh.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            fh.write(f"f {a + 1} {b + 1} {c + 1}\n")


def export_obj_face_groups(path, vertices, faces, face_groups, object_name="complete_medal"):
    """Export one complete OBJ mesh with named, shared-vertex face groups.

    The file remains one geometric solid: every group references the same vertex
    pool and every triangle is written exactly once. DCC/CAD applications can
    therefore select the front relief, side wall and flat back independently
    without receiving overlapping duplicate meshes.
    """
    vertices, faces = _mesh_arrays(vertices, faces)
    groups = []
    assigned = np.zeros(len(faces), dtype=bool)
    for raw_name, raw_indices in face_groups.items():
        name = _safe_obj_name(raw_name)
        indices = np.asarray(raw_indices, dtype=np.int64).reshape(-1)
        if indices.size:
            if indices.min() < 0 or indices.max() >= len(faces):
                raise ValueError(f"OBJ face group {name} references a face outside the mesh")
            if len(np.unique(indices)) != len(indices):
                raise ValueError(f"OBJ face group {name} contains duplicate face indices")
            if assigned[indices].any():
                raise ValueError(f"OBJ face group {name} overlaps another face group")
            assigned[indices] = True
        groups.append((name, indices))
    if len(faces) and not assigned.all():
        raise ValueError("OBJ face groups must cover every mesh face exactly once")

    with _atomic_writer(path, "w", encoding="utf-8") as fh:
        fh.write(f"o {_safe_obj_name(object_name)}\n")
        for x, y, z in vertices:
            fh.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for name, indices in groups:
            fh.write(f"g {name}\n")
            for face_index in indices:
                a, b, c = faces[int(face_index)]
                fh.write(f"f {a + 1} {b + 1} {c + 1}\n")


def single_side_surface_face_groups(vertices, faces):
    """Classify a closed single-side relief into editable surface roles."""
    vertices, faces = _mesh_arrays(vertices, faces)
    if len(faces) == 0:
        empty = np.zeros(0, dtype=np.int64)
        return {"front_relief": empty, "side_wall": empty, "flat_back": empty}

    triangles = vertices[faces]
    minimum_z = float(vertices[:, 2].min()) if len(vertices) else 0.0
    span = float(np.ptp(vertices[:, 2])) if len(vertices) else 0.0
    tolerance = max(1e-7, span * 1e-7)
    flat_back = np.all(np.abs(triangles[:, :, 2] - minimum_z) <= tolerance, axis=1)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    front_relief = (~flat_back) & (normals[:, 2] > tolerance)
    side_wall = ~(flat_back | front_relief)
    return {
        "front_relief": np.flatnonzero(front_relief),
        "side_wall": np.flatnonzero(side_wall),
        "flat_back": np.flatnonzero(flat_back),
    }


def export_obj_objects(path, objects):
    """Export multiple named mesh objects to one atomic OBJ file."""
    vertex_offset = 0
    with _atomic_writer(path, "w", encoding="utf-8") as fh:
        for item in objects:
            name = _safe_obj_name(item.get("name", "object"))
            vertices, faces = _mesh_arrays(item.get("vertices", []), item.get("faces", []))
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
    """Export an atomic ASCII STL file using millimeter coordinates."""
    verts, faces = _mesh_arrays(vertices, faces)
    with _atomic_writer(path, "w", encoding="utf-8") as fh:
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
    offset = _aligned_length(len(binary_blob))
    binary_blob = _pad_bytes(binary_blob, b"\x00") + payload
    return binary_blob, offset


def _as_nx3_array(values, dtype, name):
    try:
        data = np.asarray(values, dtype=dtype)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an Nx3 array") from exc
    if data.size == 0:
        return np.zeros((0, 3), dtype=dtype)
    if data.ndim != 2 or data.shape[1] != 3:
        raise ValueError(f"{name} must be an Nx3 array")
    return data


def _faces_array(faces):
    face_values = _as_nx3_array(faces, np.float64, "faces")
    if not np.isfinite(face_values).all():
        raise ValueError("faces must contain finite integer indices")
    if not np.equal(face_values, np.rint(face_values)).all():
        raise ValueError("faces must contain finite integer indices")
    return face_values.astype(np.int64)


def _mesh_arrays(vertices, faces):
    verts = _as_nx3_array(vertices, np.float32, "vertices")
    faces = _faces_array(faces)
    if not np.isfinite(verts).all():
        raise ValueError("vertices contain non-finite coordinates")
    if len(verts) > 0 and len(faces) > 0 and (faces.min() < 0 or faces.max() >= len(verts)):
        raise ValueError("faces contain vertex indices outside the vertex array")
    return verts, faces


def _clamp01(value, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not np.isfinite(number):
        number = float(default)
    return float(min(max(number, 0.0), 1.0))


def _base_color(item):
    raw = item.get("base_color", item.get("color", _DEFAULT_BASE_COLOR))
    if isinstance(raw, str):
        raw = raw.strip().lstrip("#")
        if len(raw) in {6, 8}:
            try:
                values = [int(raw[index : index + 2], 16) / 255.0 for index in range(0, len(raw), 2)]
            except ValueError:
                return list(_DEFAULT_BASE_COLOR)
            if len(values) == 3:
                values.append(1.0)
            return [_clamp01(value, default) for value, default in zip(values, _DEFAULT_BASE_COLOR)]
        return list(_DEFAULT_BASE_COLOR)
    try:
        values = [float(value) for value in raw]
    except (TypeError, ValueError):
        return list(_DEFAULT_BASE_COLOR)
    if len(values) == 3:
        values.append(1.0)
    if len(values) != 4:
        return list(_DEFAULT_BASE_COLOR)
    return [_clamp01(value, default) for value, default in zip(values, _DEFAULT_BASE_COLOR)]


def _material_from_item(item, name):
    return {
        "name": f"{name}_material",
        "pbrMetallicRoughness": {
            "baseColorFactor": _base_color(item),
            "metallicFactor": _clamp01(item.get("metallic", 0.0), 0.0),
            "roughnessFactor": _clamp01(item.get("roughness", 0.65), 0.65),
        },
    }


def export_glb(path, vertices, faces):
    """Export a minimal binary glTF 2.0 GLB mesh."""
    export_glb_objects(path, [{"name": "badge_relief", "vertices": vertices, "faces": faces}])


def export_glb_objects(path, objects):
    """Export multiple named mesh objects to one binary glTF 2.0 GLB file."""
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


def _aligned_length(length, alignment=4):
    return (int(length) + alignment - 1) // alignment * alignment


def _pad_bytes(data, pad_byte=b"\x00", alignment=4):
    return data + pad_byte * (_aligned_length(len(data), alignment) - len(data))


def _write_glb(path, document, binary_blob):
    json_bytes = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_bytes = _pad_bytes(json_bytes, b" ")
    binary_blob = _pad_bytes(binary_blob, b"\x00")
    chunks = [struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes]
    if binary_blob:
        chunks.append(struct.pack("<I4s", len(binary_blob), b"BIN\x00") + binary_blob)
    total_length = 12 + sum(len(chunk) for chunk in chunks)
    with _atomic_writer(path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, total_length))
        for chunk in chunks:
            fh.write(chunk)


def export_mesh(path, vertices, faces):
    """Export based on the target suffix."""
    suffix = Path(path).suffix.lower()
    if suffix == ".obj":
        export_obj(path, vertices, faces)
    elif suffix == ".stl":
        export_ascii_stl(path, vertices, faces)
    elif suffix == ".glb":
        export_glb(path, vertices, faces)
    else:
        raise ValueError(f"unsupported mesh export format: {suffix or '<none>'}")


def supported_formats():
    return {"stl", "obj", "glb"}


def implemented_formats():
    return {"obj", "stl", "glb"}
