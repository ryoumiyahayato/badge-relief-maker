"""Basic manufacturability report helpers."""


def basic_report(vertices, faces, minimum_thickness_mm=None):
    """Return a simple mesh diagnostic report."""
    return {
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        "minimum_thickness_mm": minimum_thickness_mm,
        "watertight_check": "not implemented",
        "thin_region_check": "not implemented",
    }
