"""Local mesh, footprint and process-oriented advisory analysis."""

from collections import defaultdict, deque
from heapq import heappop, heappush

import numpy as np


PROCESS_PROFILES = {
    "general": {"minimum_wall_mm": 0.8, "minimum_feature_mm": 0.4, "maximum_overhang_deg": 45.0},
    "fdm": {"minimum_wall_mm": 0.8, "minimum_feature_mm": 0.4, "maximum_overhang_deg": 45.0},
    "resin": {"minimum_wall_mm": 0.5, "minimum_feature_mm": 0.2, "maximum_overhang_deg": 35.0},
    "cnc": {"minimum_wall_mm": 1.0, "minimum_feature_mm": 0.8, "maximum_overhang_deg": 0.0},
    "mould": {"minimum_wall_mm": 1.0, "minimum_feature_mm": 0.5, "maximum_overhang_deg": 3.0},
}


def process_profile(name="general", minimum_thickness_mm=None):
    normalized = str(name or "general").strip().lower()
    if normalized not in PROCESS_PROFILES:
        raise ValueError(f"unsupported process profile: {name}")
    result = dict(PROCESS_PROFILES[normalized])
    if minimum_thickness_mm is not None:
        result["minimum_wall_mm"] = max(float(minimum_thickness_mm), result["minimum_wall_mm"])
    result["name"] = normalized
    return result


def _orientation_2d(a, b, c, epsilon):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_in_triangle_2d(point, triangle, epsilon):
    signs = [_orientation_2d(triangle[index], triangle[(index + 1) % 3], point, epsilon) for index in range(3)]
    return not (any(value > epsilon for value in signs) and any(value < -epsilon for value in signs))


def _segments_intersect_2d(a, b, c, d, epsilon):
    first = _orientation_2d(a, b, c, epsilon)
    second = _orientation_2d(a, b, d, epsilon)
    third = _orientation_2d(c, d, a, epsilon)
    fourth = _orientation_2d(c, d, b, epsilon)
    if ((first > epsilon and second < -epsilon) or (first < -epsilon and second > epsilon)) and (
        (third > epsilon and fourth < -epsilon) or (third < -epsilon and fourth > epsilon)
    ):
        return True

    def on_segment(p, q, r):
        return (
            min(p[0], r[0]) - epsilon <= q[0] <= max(p[0], r[0]) + epsilon
            and min(p[1], r[1]) - epsilon <= q[1] <= max(p[1], r[1]) + epsilon
        )

    return (
        (abs(first) <= epsilon and on_segment(a, c, b))
        or (abs(second) <= epsilon and on_segment(a, d, b))
        or (abs(third) <= epsilon and on_segment(c, a, d))
        or (abs(fourth) <= epsilon and on_segment(c, b, d))
    )


def _coplanar_triangles_intersect(first, second, normal, epsilon):
    drop_axis = int(np.argmax(np.abs(normal)))
    first_2d = np.delete(first, drop_axis, axis=1)
    second_2d = np.delete(second, drop_axis, axis=1)
    for left_index in range(3):
        for right_index in range(3):
            if _segments_intersect_2d(
                first_2d[left_index],
                first_2d[(left_index + 1) % 3],
                second_2d[right_index],
                second_2d[(right_index + 1) % 3],
                epsilon,
            ):
                return True
    return _point_in_triangle_2d(first_2d[0], second_2d, epsilon) or _point_in_triangle_2d(second_2d[0], first_2d, epsilon)


def _segment_triangle_intersection(start, end, triangle, epsilon):
    direction = end - start
    edge1 = triangle[1] - triangle[0]
    edge2 = triangle[2] - triangle[0]
    pvec = np.cross(direction, edge2)
    determinant = float(np.dot(edge1, pvec))
    if abs(determinant) <= epsilon:
        return False
    inverse = 1.0 / determinant
    tvec = start - triangle[0]
    u = float(np.dot(tvec, pvec)) * inverse
    if u < -epsilon or u > 1.0 + epsilon:
        return False
    qvec = np.cross(tvec, edge1)
    v = float(np.dot(direction, qvec)) * inverse
    if v < -epsilon or u + v > 1.0 + epsilon:
        return False
    distance = float(np.dot(edge2, qvec)) * inverse
    return -epsilon <= distance <= 1.0 + epsilon


def triangles_intersect(first, second, epsilon=1e-9):
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    if np.any(first.max(axis=0) < second.min(axis=0) - epsilon) or np.any(second.max(axis=0) < first.min(axis=0) - epsilon):
        return False
    normal_first = np.cross(first[1] - first[0], first[2] - first[0])
    normal_second = np.cross(second[1] - second[0], second[2] - second[0])
    length_first = float(np.linalg.norm(normal_first))
    length_second = float(np.linalg.norm(normal_second))
    if length_first <= epsilon or length_second <= epsilon:
        return False
    distances_second = np.dot(second - first[0], normal_first)
    distances_first = np.dot(first - second[0], normal_second)
    if np.all(distances_second > epsilon) or np.all(distances_second < -epsilon):
        return False
    if np.all(distances_first > epsilon) or np.all(distances_first < -epsilon):
        return False
    if np.linalg.norm(np.cross(normal_first, normal_second)) <= epsilon * length_first * length_second:
        if np.max(np.abs(distances_second)) <= epsilon * length_first:
            return _coplanar_triangles_intersect(first, second, normal_first, epsilon)
        return False
    for index in range(3):
        if _segment_triangle_intersection(first[index], first[(index + 1) % 3], second, epsilon):
            return True
        if _segment_triangle_intersection(second[index], second[(index + 1) % 3], first, epsilon):
            return True
    return False


def self_intersection_report(vertices, faces, max_candidate_pairs=2_000_000):
    """Detect non-adjacent triangle intersections using a uniform-grid broad phase."""
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=np.int64)
    empty = {
        "checked": True,
        "complete": True,
        "candidate_pair_count": 0,
        "tested_pair_count": 0,
        "intersection_pair_count": 0,
        "sample_face_pairs": [],
    }
    if len(faces) < 2:
        return empty
    triangles = vertices[faces]
    mins = triangles.min(axis=1)
    maxs = triangles.max(axis=1)
    overall_min = mins.min(axis=0)
    span = np.maximum(maxs.max(axis=0) - overall_min, 1e-9)
    divisions = min(36, max(4, int(round(len(faces) ** (1.0 / 3.0)))))
    cells = defaultdict(list)
    oversized = []
    for index, (minimum, maximum) in enumerate(zip(mins, maxs)):
        low = np.floor((minimum - overall_min) / span * divisions).astype(int)
        high = np.floor((maximum - overall_min) / span * divisions).astype(int)
        low = np.clip(low, 0, divisions - 1)
        high = np.clip(high, 0, divisions - 1)
        cell_count = int(np.prod(high - low + 1))
        if cell_count > 512:
            oversized.append(index)
            continue
        for x in range(low[0], high[0] + 1):
            for y in range(low[1], high[1] + 1):
                for z in range(low[2], high[2] + 1):
                    cells[(x, y, z)].append(index)

    candidates = set()
    complete = True
    for indices in cells.values():
        for left_pos, left in enumerate(indices):
            for right in indices[left_pos + 1 :]:
                pair = (left, right) if left < right else (right, left)
                candidates.add(pair)
                if len(candidates) >= max_candidate_pairs:
                    complete = False
                    break
            if not complete:
                break
        if not complete:
            break
    if complete and oversized:
        for left in oversized:
            for right in range(len(faces)):
                if left != right:
                    candidates.add((left, right) if left < right else (right, left))
                    if len(candidates) >= max_candidate_pairs:
                        complete = False
                        break
            if not complete:
                break

    intersections = []
    tested = 0
    for left, right in candidates:
        if np.intersect1d(faces[left], faces[right], assume_unique=False).size:
            continue
        if np.any(maxs[left] < mins[right] - 1e-9) or np.any(maxs[right] < mins[left] - 1e-9):
            continue
        tested += 1
        if triangles_intersect(triangles[left], triangles[right]):
            intersections.append((int(left), int(right)))
    return {
        "checked": True,
        "complete": bool(complete),
        "candidate_pair_count": int(len(candidates)),
        "tested_pair_count": int(tested),
        "intersection_pair_count": int(len(intersections)),
        "sample_face_pairs": [list(pair) for pair in intersections[:20]],
    }


def _mask_components(mask):
    rows, cols = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    components = []
    for start_row, start_col in zip(*np.nonzero(mask)):
        if visited[start_row, start_col]:
            continue
        queue = deque([(int(start_row), int(start_col))])
        visited[start_row, start_col] = True
        pixels = []
        while queue:
            row, col = queue.popleft()
            pixels.append((row, col))
            for next_row, next_col in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if 0 <= next_row < rows and 0 <= next_col < cols and mask[next_row, next_col] and not visited[next_row, next_col]:
                    visited[next_row, next_col] = True
                    queue.append((next_row, next_col))
        components.append(pixels)
    return components


def _distance_to_background(mask, cell_w, cell_h):
    rows, cols = mask.shape
    distances = np.full(mask.shape, np.inf, dtype=float)
    queue = []
    for row, col in zip(*np.nonzero(mask)):
        candidates = []
        if row == 0 or not mask[row - 1, col]:
            candidates.append(cell_h / 2.0)
        if row == rows - 1 or not mask[row + 1, col]:
            candidates.append(cell_h / 2.0)
        if col == 0 or not mask[row, col - 1]:
            candidates.append(cell_w / 2.0)
        if col == cols - 1 or not mask[row, col + 1]:
            candidates.append(cell_w / 2.0)
        if candidates:
            distances[row, col] = min(candidates)
            heappush(queue, (distances[row, col], int(row), int(col)))
    neighbors = [(-1, 0, cell_h), (1, 0, cell_h), (0, -1, cell_w), (0, 1, cell_w)]
    diagonal = float(np.hypot(cell_w, cell_h))
    neighbors.extend([(-1, -1, diagonal), (-1, 1, diagonal), (1, -1, diagonal), (1, 1, diagonal)])
    while queue:
        distance, row, col = heappop(queue)
        if distance > distances[row, col] + 1e-12:
            continue
        for row_delta, col_delta, weight in neighbors:
            next_row, next_col = row + row_delta, col + col_delta
            if 0 <= next_row < rows and 0 <= next_col < cols and mask[next_row, next_col]:
                candidate = distance + weight
                if candidate < distances[next_row, next_col]:
                    distances[next_row, next_col] = candidate
                    heappush(queue, (candidate, next_row, next_col))
    return distances


def footprint_feature_report(mask, heightmap, width_mm, height_mm, base_thickness_mm, relief_height_mm, profile_name="general", minimum_thickness_mm=None):
    mask = np.asarray(mask, dtype=bool)
    heightmap = np.asarray(heightmap, dtype=float)
    profile = process_profile(profile_name, minimum_thickness_mm)
    rows, cols = mask.shape
    cell_w = float(width_mm) / float(max(cols, 1))
    cell_h = float(height_mm) / float(max(rows, 1))
    components = _mask_components(mask)
    distance = _distance_to_background(mask, cell_w, cell_h)
    local_maxima = []
    for row, col in zip(*np.nonzero(mask)):
        value = distance[row, col]
        neighbors = distance[max(0, row - 1) : min(rows, row + 2), max(0, col - 1) : min(cols, col + 2)]
        if value >= np.max(neighbors) - 1e-12:
            local_maxima.append(float(value * 2.0))
    minimum_feature = min(local_maxima) if local_maxima else 0.0
    vertical = float(base_thickness_mm) + np.clip(heightmap[mask], 0.0, 1.0) * float(relief_height_mm)
    minimum_vertical = float(vertical.min()) if vertical.size else 0.0
    pixel_area = cell_w * cell_h
    component_areas = [len(component) * pixel_area for component in components]
    tiny_threshold_area = profile["minimum_feature_mm"] ** 2
    tiny_indices = [index for index, area in enumerate(component_areas) if area < tiny_threshold_area]
    return {
        "process_profile": profile,
        "geometry_cell_size_mm_xy": [cell_w, cell_h],
        "local_wall_thickness": {
            "minimum_vertical_thickness_mm": minimum_vertical,
            "required_minimum_mm": profile["minimum_wall_mm"],
            "violation": bool(minimum_vertical + 1e-9 < profile["minimum_wall_mm"]),
        },
        "minimum_feature_size": {
            "estimated_minimum_mm": float(minimum_feature),
            "required_minimum_mm": profile["minimum_feature_mm"],
            "violation": bool(minimum_feature + 1e-9 < profile["minimum_feature_mm"]),
            "method": "foreground distance-ridge estimate",
        },
        "floating_components": {
            "component_count": len(components),
            "component_areas_mm2": component_areas,
            "tiny_component_indices": tiny_indices,
            "tiny_component_count": len(tiny_indices),
        },
    }


def overhang_tool_access_report(vertices, faces, profile_name="general"):
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=np.int64)
    profile = process_profile(profile_name)
    if len(faces) == 0:
        return {"profile": profile_name, "unsupported_face_count": 0, "review_required": False}
    triangles = vertices[faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    unit_z = np.zeros(len(faces), dtype=float)
    unit_z[valid] = normals[valid, 2] / lengths[valid]
    centroids_z = triangles[:, :, 2].mean(axis=1)
    bottom = float(vertices[:, 2].min())
    threshold = -np.cos(np.deg2rad(90.0 - profile["maximum_overhang_deg"]))
    unsupported = valid & (unit_z < threshold) & (centroids_z > bottom + 1e-6)
    count = int(np.count_nonzero(unsupported))
    return {
        "profile": profile_name,
        "maximum_overhang_deg": profile["maximum_overhang_deg"],
        "unsupported_face_count": count,
        "review_required": bool(count > 0 or profile_name in {"cnc", "mould"}),
        "note": "orientation-only advisory; tool diameter, mould draft direction and support strategy still require review",
    }
