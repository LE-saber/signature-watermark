"""Synthetic signature photos with a known ink mask, for background-removal tests.

Each case returns (RGB image, ground-truth ink mask). The signature is drawn on its
own layer first, so the mask is exact.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 900, 380


def _signature_layer(rng, ink=(25, 45, 140), width=6):
    layer = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(layer)
    pts = []
    for i in range(500):
        t = i / 499
        x = 110 + t * 660
        y = 200 + 75 * math.sin(t * 17 + 0.6) * math.cos(t * 4) + rng.uniform(-1.5, 1.5)
        pts.append((x, y))
    d.line(pts, fill=255, width=width, joint="curve")
    d.line([(150, 300), (560, 285)], fill=255, width=width - 2)       # short underline flourish
    d.ellipse([640, 92, 654, 106], fill=255)                          # a dot
    return layer, ink


def _compose(paper: np.ndarray, layer: Image.Image, ink) -> tuple[Image.Image, np.ndarray]:
    a = np.asarray(layer, dtype=np.float32)[:, :, None] / 255
    out = paper.astype(np.float32) * (1 - a) + np.array(ink, np.float32) * a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), np.asarray(layer) > 128


def _jpeg(img: Image.Image, q=85) -> Image.Image:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=q)
    b.seek(0)
    return Image.open(b).convert("RGB")


def ruled(seed=1):
    rng = np.random.default_rng(seed)
    p = Image.new("RGB", (W, H), (250, 250, 246))
    d = ImageDraw.Draw(p)
    for y in range(40, H, 34):
        d.line([(0, y), (W, y + 3)], fill=(150, 185, 225), width=2)   # slightly skewed blue rules
    d.line([(70, 0), (70, H)], fill=(225, 120, 120), width=2)         # red margin
    layer, ink = _signature_layer(rng)
    img, gt = _compose(np.asarray(p), layer, ink)
    return _jpeg(img), gt


def grid(seed=2):
    rng = np.random.default_rng(seed)
    p = Image.new("RGB", (W, H), (252, 252, 252))
    d = ImageDraw.Draw(p)
    for x in range(0, W, 22):
        d.line([(x, 0), (x, H)], fill=(170, 200, 170), width=1)
    for y in range(0, H, 22):
        d.line([(0, y), (W, y)], fill=(170, 200, 170), width=1)
    layer, ink = _signature_layer(rng, ink=(20, 20, 20))
    img, gt = _compose(np.asarray(p), layer, ink)
    return _jpeg(img), gt


def form_box(seed=3):
    rng = np.random.default_rng(seed)
    p = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(p)
    d.rectangle([12, 14, W - 14, H - 12], outline=(40, 40, 40), width=3)   # printed form cell
    d.line([(12, 70), (W - 14, 70)], fill=(40, 40, 40), width=2)
    layer, ink = _signature_layer(rng, ink=(15, 30, 110))
    img, gt = _compose(np.asarray(p), layer, ink)
    return _jpeg(img), gt


def form_cross(seed=7):
    """Black pen crossing black printed form lines: same darkness, only geometry tells them apart."""
    rng = np.random.default_rng(seed)
    p = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(p)
    for y in (120, 200, 280):
        d.line([(0, y), (W, y)], fill=(25, 25, 25), width=2)
    layer, ink = _signature_layer(rng, ink=(20, 20, 20))
    img, gt = _compose(np.asarray(p), layer, ink)
    return _jpeg(img), gt


def desk_photo(seed=4):
    """Paper photographed on a wooden desk: dark textured strip, paper edge, shadow, noise."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    paper = np.empty((H, W, 3), np.float32)
    light = 0.78 + 0.22 * (xx / W) * (0.85 + 0.15 * (yy / H))          # uneven lighting
    paper[:] = np.array([246, 242, 232], np.float32)
    paper *= light[:, :, None]
    wood = np.array([95, 62, 38], np.float32) * (0.8 + 0.4 * (0.5 + 0.5 * np.sin(yy / 6 + 3 * np.sin(xx / 40))))[:, :, None]
    edge = 60 + 8 * np.sin(yy / 50)                                    # paper edge, not straight
    desk = (xx < edge)[:, :, None]
    base = np.where(desk, wood, paper)
    base += rng.normal(0, 4, base.shape)
    layer, ink = _signature_layer(rng, ink=(30, 35, 60))
    img, gt = _compose(np.clip(base, 0, 255), layer, ink)
    return _jpeg(img.filter(ImageFilter.GaussianBlur(0.6)), 80), gt


def recycled(seed=5):
    """Grey textured paper with fibres and dark specks."""
    rng = np.random.default_rng(seed)
    base = np.full((H, W, 3), 228, np.float32) + rng.normal(0, 6, (H, W, 1))
    p = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
    d = ImageDraw.Draw(p)
    for _ in range(140):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.uniform(0.6, 1.8)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(int(rng.uniform(70, 140)),) * 3)
    for _ in range(40):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        a = rng.uniform(0, math.pi)
        d.line([(x, y), (x + 14 * math.cos(a), y + 14 * math.sin(a))], fill=(185, 180, 170), width=1)
    layer, ink = _signature_layer(rng, ink=(20, 30, 90))
    img, gt = _compose(np.asarray(p), layer, ink)
    return _jpeg(img), gt


def plain(seed=6):
    rng = np.random.default_rng(seed)
    p = np.full((H, W, 3), 250, np.uint8)
    layer, ink = _signature_layer(rng)
    img, gt = _compose(p, layer, ink)
    return _jpeg(img), gt


CASES = {"plain": plain, "ruled": ruled, "grid": grid, "form_box": form_box, "form_cross": form_cross,
         "desk_photo": desk_photo,
         "recycled": recycled}


def score(alpha: np.ndarray, gt: np.ndarray) -> tuple[float, float]:
    """(ink kept, junk kept): share of true ink retained, and kept pixels that are not ink."""
    kept = alpha > 128
    near = np.asarray(Image.fromarray(gt.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(5))) > 0
    recall = float((kept & gt).sum() / max(1, gt.sum()))
    junk = float((kept & ~near).sum() / max(1, kept.sum()))
    return recall, junk
