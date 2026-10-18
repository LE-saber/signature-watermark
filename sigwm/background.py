"""Extract dark or colored pen strokes from white/light paper using local paper estimates."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def has_paper_background(image: Image.Image) -> bool:
    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A"))
    if alpha.min() == 255:
        return True
    # Rounded paper cutouts may have transparent corners but still contain an
    # opaque paper rectangle. Distinguish those from an actual ink-only PNG.
    opaque = alpha >= 250
    bbox = Image.fromarray(opaque).getbbox()
    if bbox is None:
        return False
    l, t, r, b = bbox
    rgb = np.asarray(rgba, dtype=np.float32)[t:b, l:r, :3]
    light = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32) > 180
    return float((light & opaque[t:b, l:r]).mean()) > 0.6


def remove_paper(image: Image.Image, threshold: int = 220) -> Image.Image:
    """Return straight-alpha ink, compensating for paper tint and gradual shadows.

    Ink-only transparent input is kept unchanged; an opaque paper region inside
    a partially transparent PNG is still removed. Intended for cropped signatures.
    """
    rgba = image.convert("RGBA")
    if not has_paper_background(rgba):
        return rgba
    rgb = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")
    paper = rgb.copy()
    paper.thumbnail((768, 768), Image.Resampling.BOX)
    kernel = max(15, min(65, (min(paper.size) // 12) | 1))
    paper = paper.filter(ImageFilter.MaxFilter(kernel)).filter(ImageFilter.GaussianBlur(kernel / 3))
    paper = paper.resize(rgb.size, Image.Resampling.BILINEAR)
    pixels = np.asarray(rgb, dtype=np.float32)
    illumination = np.maximum(np.asarray(paper, dtype=np.float32), 1)
    normalized = np.clip(pixels * 255 / illumination, 0, 255)
    luminance = normalized @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    alpha = np.round(np.clip((threshold - luminance) / 24, 0, 1) * 255).astype(np.uint8)
    alpha = np.minimum(alpha, np.asarray(rgba.getchannel("A")))
    a = alpha[:, :, None].astype(np.float32) / 255
    # Remove the paper matte from edge pixels so the PNG has no pale fringes.
    ink = np.clip((normalized - 255 * (1 - a)) / np.maximum(a, 1 / 255), 0, 255)
    ink[alpha == 0] = 0
    return Image.fromarray(np.dstack((np.round(ink).astype(np.uint8), alpha)))
