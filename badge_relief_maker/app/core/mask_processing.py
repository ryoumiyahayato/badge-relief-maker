"""Mask and heightmap processing helpers."""

import math
from collections import deque

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def mask_bbox(mask, padding=0):
    """Return a padded bounding box as x0, y0, x1, y1."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    height, width = mask.shape
    x0 = max(int(xs.min()) - int(padding), 0)
    y0 = max(int(ys.min()) - int(padding), 0)
    x1 = min(int(xs.max()) + int(padding) + 1, width)
    y1 = min(int(ys.max()) + int(padding) + 1, height)
    return x0, y0, x1, y1


def _neighbors4(y, x, height, width):
    if y > 0:
        yield y - 1, x
    if y < height - 1:
        yield y + 1, x
    if x > 0:
        yield y, x - 1
    if x < width - 1:
        yield y, x + 1


def _component_labels(mask_value, target=True):
    """Return connected components for target pixels."""
    mask_value = mask_value.astype(bool)
    height, width = mask_value.shape
    visited = np.zeros_like(mask_value, dtype=bool)
    components = []

    for y in range(height):
        for x in range(width):
            if visited[y, x] or bool(mask_value[y, x]) != bool(target):
                continue
            queue = deque([(y, x)])
            visited[y, x] = True
            pixels = []
            touches_border = False
            while queue:
                cy, cx = queue.popleft()
                pixels.append((cy, cx))
                if cy == 0 or cx == 0 or cy == height - 1 or cx == width - 1:
                    touches_border = True
                for ny, nx in _neighbors4(cy, cx, height, width):
                    if not visited[ny, nx] and bool(mask_value[ny, nx]) == bool(target):
                        visited[ny, nx] = True
                        queue.append((ny, nx))
            components.append((pixels, touches_border))
    return components


def remove_small_components(mask, min_pixels=1):
    """Remove foreground islands smaller than min_pixels."""
    if min_pixels is None or int(min_pixels) <= 1:
        return mask.astype(bool), 0
    result = mask.astype(bool).copy()
    removed = 0
    for pixels, _ in _component_labels(result, target=True):
        if len(pixels) < int(min_pixels):
            removed += len(pixels)
            for y, x in pixels:
                result[y, x] = False
    return result, removed


def fill_small_holes(mask, max_pixels=0):
    """Fill background holes smaller than max_pixels that do not touch border."""
    if max_pixels is None or int(max_pixels) <= 0:
        return mask.astype(bool), 0
    result = mask.astype(bool).copy()
    filled = 0
    for pixels, touches_border in _component_labels(result, target=False):
        if not touches_border and len(pixels) <= int(max_pixels):
            filled += len(pixels)
            for y, x in pixels:
                result[y, x] = True
    return result, filled


def majority_smooth_mask(mask, iterations=0):
    """Apply a small 3x3 majority filter to reduce single-pixel jagged noise."""
    result = mask.astype(bool).copy()
    for _ in range(max(0, int(iterations))):
        padded = np.pad(result, 1, mode="edge")
        score = np.zeros_like(result, dtype=np.int16)
        for dy in range(3):
            for dx in range(3):
                score += padded[dy : dy + result.shape[0], dx : dx + result.shape[1]]
        result = score >= 5
    return result


def clean_mask(mask, min_component_pixels=1, fill_hole_pixels=0, smooth_iterations=0):
    """Run conservative local mask cleanup and return metadata."""
    cleaned, removed_pixels = remove_small_components(mask, min_component_pixels)
    cleaned, filled_pixels = fill_small_holes(cleaned, fill_hole_pixels)
    cleaned = majority_smooth_mask(cleaned, smooth_iterations)
    return cleaned, {
        "removed_small_component_pixels": int(removed_pixels),
        "filled_hole_pixels": int(filled_pixels),
        "smooth_iterations": int(max(0, smooth_iterations)),
    }



def regularize_binary_contour(mask, sigma=0.86):
    """Remove one-pixel edge bumps without flattening established interior detail.

    Only the narrow signed-distance band around the silhouette is changed. Pixels
    more than roughly 1.5 source pixels inside or outside remain fixed, so thin leaf
    tips and engraving cut-outs are less likely to disappear than with a global
    morphological opening/closing operation.
    """
    source = np.asarray(mask, dtype=bool)
    if not source.any() or source.all():
        return source.copy()
    inside = ndi.distance_transform_edt(source)
    outside = ndi.distance_transform_edt(~source)
    signed = (inside - outside).astype(np.float32)
    smoothed = ndi.gaussian_filter(signed, sigma=max(float(sigma), 0.0))
    result = smoothed >= 0.0
    result[signed >= 2.05] = True
    result[signed <= -2.05] = False
    return np.asarray(result, dtype=bool)


def resample_binary_mask(mask, target_shape):
    """Resample a binary silhouette through a regularized signed-distance field.

    The contour is first cleaned only inside a narrow boundary band, then the
    signed distance is interpolated. A final subpixel Gaussian pass suppresses the
    isolated staircase dots that otherwise remain visible even on dense meshes.
    """
    source = regularize_binary_contour(mask)
    rows, cols = [int(value) for value in target_shape]
    if source.shape == (rows, cols):
        return source.copy()
    if rows < 1 or cols < 1:
        raise ValueError("target_shape must be positive")
    inside = ndi.distance_transform_edt(source)
    outside = ndi.distance_transform_edt(~source)
    signed = ndi.gaussian_filter((inside - outside).astype(np.float32), sigma=0.32)
    image = Image.fromarray(signed, mode="F")
    resized = np.asarray(image.resize((cols, rows), Image.Resampling.BICUBIC), dtype=np.float32)
    resized = ndi.gaussian_filter(resized, sigma=0.36)
    return resized >= 0.0


def resample_mask_and_heightmap(mask, heightmap, target_cells):
    """Resample a relief field toward a target mesh density.

    ThhИ[\€Ш[€\ШШ[HЭЛ\™\ЫЫ][Ы€ЫЭ\ЩH\ќЫЬљИ™Y›Ь™HY\ЪЩ[™\][ЫЋВ€HЬ™[\ћH™]љY]И]™[XZ[њИ›Э[™YћHHЬљYЪ[[[XYЩHЪ^™K‚€€€‚€›ЭЬЛЫЫИHњ\Ш\њ^JX\ЪКKњЪ\B€Э\њ™[ќHX^
›ЭЬИ
€ЫЫЛJB€\™Щ]HX^
[ќ
\™Щ]ШЩ[КK
B€ШШ[HHX]њЬ\ќ
›Ш]
\™Щ]
HИ›Ш]
Э\њ™[ќ
JB€™]ЧЬ›ЭЬИHX^
‹[ќ
›Э[™
›ЭЬИ
€ШШ[JJJB€™]ЧШЫЫИHX^
‹[ќ
›Э[™
ЫЫИ
€ШШ[JJJB€™\Ъ^™YЫX\ЪИH™\Ш[\WШљ[\ћWЫX\ЪКX\ЪЛ
™]ЧЬ›ЭЬЛ™]ЧШЫЫКJB€ZYЪЪ[YИH[XYЩK™њ›ЫX\њ^Jњ\Ш\њ^JZYЪX\\O[њ™›Ш]МЉK[ЩOH‘€ЉB€™\Ъ^™YЪZYЪHњ\Ш\њ^JZYЪЪ[YЛњ™\Ъ^™J
™]ЧШЫЫЛ™]ЧЬ›ЭЬКK[XYЩK”™\Ш[\[™Лђ’PХP’PКK\O[њ™›Ш]МЉB€™\Ъ^™YЪZYЪHњќЪ\™J™\Ъ^™YЫX\ЪЛњЫ\
™\Ъ^™YЪZYЪЊKЊ
KЊ
K\Э\Jњ™›Ш]МЉB€™]\›€™\Ъ^™YЫX\ЪЛ™\Ъ^™YЪZYЪ›Ш]
ШШ[JB‚™Y€Ь›ЬЭЧЫX\ЪКX\ЪЛZYЪX\Y[™ПLJN‚€€€ђЬ›ЬX\ЪИ[™ZYЪX\ИH›Ь™YЬ›Э[™›Э[™[™И›Ю€€€‚€›ЮHX\ЪЧШ›Ю
X\ЪЛY[™П\Y[™КB€Y€›Ю\И›Ы™N‚€™]\›€X\ЪЛZYЪX\›Ы™B€LKLHH›Ю€™]\›€X\ЪЦЮLћLKћWKZYЪX\ЮLћLKћWK›Ю‚‚™Y€™\Ъ^™WЫX\ЪЧШ[™ЪZYЪX\
X\ЪЛZYЪX\X^ШЩ[КN‚€€€‘ЭЫњШ[\HX\ЪИ[™ZYЪX\Ъ[€HЬљY\ИЫИ\™ЩK€€€‚€Y€X^ШЩ[И\И›Ы™HЬ€X^ШЩ[ИH‚€™]\›€X\ЪЛZYЪX\KЊ‚€›ЭЬЛЫЫИHX\ЪЛњЪ\B€Э\њ™[ќH›ЭЬИ
€ЫЫВ€Y€Э\њ™[ќHX^ШЩ[О‚€™]\›€X\ЪЛZYЪX\KЊ‚€ШШ[HHX]њЬ\ќ
›Ш]
X^ШЩ[КHИ›Ш]
Э\њ™[ќ
JB€™]ЧШЫЫИHX^
‹[ќ
ЫЫИ
€ШШ[JJB€™]ЧЬ›ЭЬИHX^
‹[ќ
›ЭЬИ
€ШШ[JJB‚€™\Ъ^™YЫX\ЪИH™\Ш[\WШљ[\ћWЫX\ЪКX\ЪЛ
™]ЧЬ›ЭЬЛ™]ЧШЫЫКJB€ZYЪЪ[YИH[XYЩK™њ›ЫX\њ^Jњ\Ш\њ^JZYЪX\\O[њ™›Ш]МЉK[ЩOH‘€ЉB€™\Ъ^™YЪZYЪHњ\Ш\њ^JZYЪЪ[YЛњ™\Ъ^™J
™]ЧШЫЫЛ™]ЧЬ›ЭЬКK[XYЩK”™\Ш[\[™Лђ’PХP’PКK\O[њ™›Ш]МЉB€™\Ъ^™YЪZYЪHњќЪ\™J™\Ъ^™YЫX\ЪЛњЫ\
™\Ъ^™YЪZYЪЊKЊ
KЊ
K\Э\Jњ™›Ш]МЉB€™]\›€™\Ъ^™YЫX\ЪЛ™\Ъ^™YЪZYЪ›Ш]
ШШ[JB