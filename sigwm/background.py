"""Extract dark or colored pen strokes from white/light paper using local paper estimates.

After the paper colour is removed, clean_ink() drops what is not handwriting:
ruled/grid/form lines (keeping the points where strokes cross them), solid dark
areas such as a desk, a shadow or a finger, and isolated specks.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from . import imgops


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


def remove_paper(image: Image.Image, threshold: int = 220, clean: bool = True) -> Image.Image:
    """Return straight-alpha ink, compensating for paper tint and gradual shadows.

    Ink-only transparent input is kept unchanged; an opaque paper region inside
    a partially transparent PNG is still removed. Intended for cropped signatures.
    """
    rgba = image.convert("RGBA")
    if not has_paper_background(rgba):
        return rgba
    if clean and max(rgba.size) < 700:
        # Small photos: the cleanup reasons in pixels (stroke width, texture patches), so
        # decide what to keep at twice the size, then apply that to the full-quality
        # result at the original size. Kept ink pixels are not resampled.
        plain = remove_paper(rgba, threshold, clean=False)
        big = remove_paper(rgba.resize((rgba.width * 2, rgba.height * 2), Image.Resampling.BICUBIC),
                           threshold, clean=True)
        kept = np.asarray(big.getchannel("A")) > 0
        h2, w2 = rgba.height, rgba.width
        kept = kept[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2).any(axis=(1, 3))
        out = np.asarray(plain).copy()
        out[~kept] = 0
        return Image.fromarray(out)
    rgb = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")
    paper = rgb.copy()
    # Lighting changes slowly, so estimate it on a small copy (a large-kernel max filter
    # on a big image took seconds).
    paper.thumbnail((256, 256), Image.Resampling.BOX)
    kernel = max(5, min(21, (min(paper.size) // 12) | 1))
    paper = paper.filter(ImageFilter.MaxFilter(kernel)).filter(ImageFilter.GaussianBlur(kernel / 3))
    paper = paper.resize(rgb.size, Image.Resampling.BILINEAR)
    pixels = np.asarray(rgb, dtype=np.float32)
    # Large dark areas (desk, background around the sheet, deep shadow) must go before the
    # illumination estimate below, which would otherwise "whiten" them into stripes.
    raw = pixels @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    paper_level = float(np.percentile(raw, 90))
    k = max(15, min(rgb.size) // 25)
    chroma = pixels.max(axis=2) - pixels.min(axis=2)
    # dark, or clearly coloured and not bright (a brown or purple desk, with highlights)
    dark = (raw < paper_level * 0.62) | ((chroma > 45) & (raw < paper_level * 0.85))
    not_paper = imgops.dilate(imgops.erode(dark, k, k), k + 6, k + 6)
    # thinner strips of desk along the edge: solid regions connected to the border
    h, w = dark.shape
    labels, stats = imgops.label(dark)
    for i in range(1, len(stats)):
        x, y, bw, bh, area = stats[i]
        if (x == 0 or y == 0 or x + bw >= w or y + bh >= h) and area > 0.005 * h * w and \
                area > 0.2 * bw * bh:
            not_paper[labels == i] = True
    not_paper = imgops.dilate(not_paper, 7, 7)
    illumination = np.maximum(np.asarray(paper, dtype=np.float32), 1)
    normalized = np.clip(pixels * 255 / illumination, 0, 255)
    luminance = normalized @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    alpha = np.round(np.clip((threshold - luminance) / 24, 0, 1) * 255).astype(np.uint8)
    alpha = np.minimum(alpha, np.asarray(rgba.getchannel("A")))
    if clean:
        alpha[not_paper] = 0
        # Hysteresis: faint pixels count only when connected to clearly dark ink. Paper
        # texture and mottling never get that dark, a stroke's soft edge is attached to it.
        cand = alpha > 0
        # seeds: clearly dark ink; for a faint signature (threshold raised by the user) its
        # own darkest pixels are the seeds
        seed_level = threshold - 45
        if cand.any():
            seed_level = max(seed_level, float(np.percentile(luminance[cand], 20)))
        strong = (luminance <= seed_level) & cand
        labels, _ = imgops.label(alpha > 0)
        seeded = np.zeros(labels.max() + 1, bool)
        seeded[np.unique(labels[strong])] = True
        seeded[0] = False
        alpha[~seeded[labels]] = 0
        # texture touching a stroke is still seeded through it; faint ink is thin, while
        # paper mottling forms wide patches that never get dark
        weak_only = (alpha > 0) & ~imgops.dilate(strong, 5, 5)
        fat = imgops.dilate(imgops.erode(weak_only, 5, 5), 7, 7) & weak_only
        alpha[fat] = 0
        alpha = clean_ink(alpha, luminance)
    a = alpha[:, :, None].astype(np.float32) / 255
    # Remove the paper matte from edge pixels so the PNG has no pale fringes.
    ink = np.clip((normalized - 255 * (1 - a)) / np.maximum(a, 1 / 255), 0, 255)
    ink[alpha == 0] = 0
    return Image.fromarray(np.dstack((np.round(ink).astype(np.uint8), alpha)))


# ---------------------------------------------------------------- cleanup

def _line_mask(m: np.ndarray, vertical: bool, dark: np.ndarray | None = None,
               ink_dark: float | None = None, span: tuple[int, int] | None = None) -> np.ndarray:
    """Pixels of long straight lines that look printed (ruled paper, grids, form cells).

    m should include faint pixels, so light printed rules come out as whole lines.
    dark: darkness (255 - luminance) used to tell a printed rule from the signer's stroke.
    """
    if vertical:
        return _line_mask(m.T, False, None if dark is None else dark.T, ink_dark,
                          None if span is None else (span[1], span[0])).T
    h, w = m.shape
    length = max(30, w // 8)
    md = imgops.dilate(m, 3, 1)                         # tolerate a slight skew
    straight = imgops.dilate(imgops.erode(md, 1, length), 1, length) & md
    labels, stats = imgops.label(straight)
    lines = []
    for k in range(1, len(stats)):
        x, y, bw, bh, area = stats[k]
        if bw >= length and bh <= max(9, 0.06 * h):
            sel = ((labels == k) & m)[:, x:x + bw]
            # medians per column, so places where strokes cross the line do not count
            thickness = float(np.median(sel.sum(axis=0)))
            darkness = float(np.median(dark[:, x:x + bw][sel])) if dark is not None and sel.any() else 0.0
            lines.append((k, x, bw, thickness, darkness))
    keep = np.zeros(len(stats), bool)
    long_lines = [ln for ln in lines if ln[2] >= 0.5 * w]
    t_med = np.median([ln[3] for ln in long_lines]) if long_lines else 0
    d_med = np.median([ln[4] for ln in long_lines]) if long_lines else 0
    for k, x, bw, thickness, darkness in lines:
        edge_to_edge = x <= 0.04 * w and x + bw >= 0.96 * w
        # a lone rule that no longer reaches both edges (tilted photo, margin line):
        # long, and clearly lighter than the ink
        # (span: the unrotated image size, as a straightened canvas is larger)
        full = w if span is None else span[1]
        lone_rule = bw >= 0.85 * full and ink_dark is not None and ink_dark - darkness > 60
        # ruled paper, grids and forms repeat the same line (also as broken pieces);
        # the signer's underline differs from them in weight or darkness
        similar = abs(thickness - t_med) <= 1.5 and abs(darkness - d_med) <= 45
        # long lines: three alike make a family (form cells). Shorter pieces only count on
        # a page full of rules (ruled/grid paper), where they are broken-up rules
        family = similar and (len(long_lines) >= 3 if bw >= 0.5 * w else len(long_lines) >= 5)
        keep[k] = edge_to_edge or family or lone_rule
    out = keep[labels] & m
    if dark is not None and out.any():
        # a rule can merge with a stroke it touches; remove only pixels as light as the rules
        ref = d_med if long_lines else float(np.median(dark[out]))
        out &= np.abs(dark - ref) <= 60
    return out


def _crossings(m: np.ndarray, band: np.ndarray, line: np.ndarray, reach: int) -> np.ndarray:
    """Pixels of a line band where a stroke passes straight through the line.

    A pixel is kept when ink lies on both sides of the line at mirrored points
    (y-d, x+o) and (y+d, x-o): a stroke crossing at any angle up to ~65 degrees from
    the line's normal. Pixels of the rule beside the crossing have no such pair.
    Ink right next to the line is ignored, or every rule would look crossed.
    Only the band's pixels are tested.
    """
    other = m & ~imgops.dilate(line, 7, 7)
    pad = 3 * reach
    p = np.pad(other, pad)
    ys, xs = np.nonzero(band)
    ys, xs = ys + pad, xs + pad
    hit = np.zeros(len(ys), bool)
    for d in range(4, reach + 1):
        for o in range(-2 * d, 2 * d + 1):
            hit |= p[ys - d, xs + o] & p[ys + d, xs - o]      # across a horizontal line
            hit |= p[ys + o, xs - d] & p[ys - o, xs + d]      # across a vertical line
    out = np.zeros_like(band)
    out[ys[hit] - pad, xs[hit] - pad] = True
    return out


def _rotate(a: np.ndarray, deg: float, size: tuple[int, int] | None = None) -> np.ndarray:
    """Rotate a 2-D array about its centre (PIL convention: counter-clockwise)."""
    is_bool = a.dtype == bool
    img = Image.fromarray(a.astype(np.uint8) * 255 if is_bool else np.clip(a, 0, 255).astype(np.uint8))
    out = img.rotate(deg, Image.Resampling.NEAREST if is_bool else Image.Resampling.BILINEAR, expand=size is None)
    r = np.asarray(out)
    if size is not None:
        h, w = size
        H, W = r.shape
        r = r[(H - h) // 2:(H - h) // 2 + h, (W - w) // 2:(W - w) // 2 + w]
    return r > 127 if is_bool else r.astype(np.float32)


def _rule_angle(m: np.ndarray) -> float:
    """Tilt of printed rules in degrees (photos are rarely square to the page)."""
    small = Image.fromarray(m.astype(np.uint8) * 255)
    small.thumbnail((400, 400), Image.Resampling.BOX)
    best, score0 = (0.0, -1.0), None
    for deg in np.arange(-10, 10.01, 0.5):
        r = np.asarray(small.rotate(float(deg), Image.Resampling.BILINEAR), dtype=np.float64)
        rows, cols = r.sum(axis=1), r.sum(axis=0)
        score = float((rows ** 2).sum() + (cols ** 2).sum())
        if deg == 0:
            score0 = score
        if score > best[1]:
            best = (float(deg), score)
    return best[0] if score0 is not None and best[1] > 1.15 * score0 else 0.0


def _stroke_width(m: np.ndarray) -> int:
    runs_h = imgops.run_lengths(m)
    runs_v = imgops.run_lengths(m.T)
    if len(runs_h) < 5 or len(runs_v) < 5:
        return 3
    return int(np.clip(min(np.median(runs_h), np.median(runs_v)), 1, 40))


def clean_ink(alpha: np.ndarray, luma: np.ndarray | None = None) -> np.ndarray:
    """Keep handwriting in an ink alpha map; drop printed lines, solid areas and specks.

    luma: luminance after paper normalisation (0 = black), used to tell faint printed
    rules from pen strokes. Without it only the line geometry is used.
    """
    m = alpha > 128
    h, w = m.shape
    if m.sum() < 30:
        return alpha
    removed = np.zeros_like(m)

    # 1. ruled lines, grids and form borders, keeping the points where strokes cross them
    dark = None if luma is None else 255.0 - luma
    faint = alpha > 48
    angle = _rule_angle(faint)
    ink_ref = float(np.percentile(dark[m], 70)) if dark is not None else None   # the darker ink
    if angle:
        # straighten, find the rules, and turn the result back
        f2, d2 = _rotate(faint, angle), None if dark is None else _rotate(dark, angle)
        found = _line_mask(f2, False, d2, ink_ref, m.shape) | _line_mask(f2, True, d2, ink_ref, m.shape)
        lines = _rotate(found, -angle, size=m.shape) & m
    else:
        lines = (_line_mask(faint, False, dark, ink_ref) | _line_mask(faint, True, dark, ink_ref)) & m
    if lines.any():
        thick = int(np.clip(np.median(imgops.run_lengths(lines.T)), 1, 8))
        band = imgops.dilate(lines, 3, 3) & m
        line_dark = float(np.median(dark[lines])) if dark is not None else None
        ink_dark = float(np.median(dark[m & ~band])) if dark is not None and (m & ~band).any() else None
        if line_dark is not None and ink_dark is not None and ink_dark - line_dark > 60:
            # printed rules clearly lighter than the ink: decide by darkness alone, so
            # crossings keep exactly the stroke and nothing of the rule
            # grainy ballpoint ink has light specks inside the stroke: drop a light pixel
            # only where no stroke passes through
            lines = band & (dark < (line_dark + ink_dark) / 2) & ~_crossings(m, band, lines, thick + 8)
        else:
            lines = band & ~_crossings(m, band, lines, thick + 8)
        removed |= lines
        m = m & ~lines

    sw = _stroke_width(m)

    # 2. solid regions much thicker than a pen stroke: desk, shadows, fingers, pens
    k = max(21, 3 * sw)            # an i-dot or a pen blob is smaller than this
    core = imgops.erode(m, k, k)
    if core.any():
        # where strokes cross or loop tightly a few core pixels survive; a desk or a
        # finger leaves a core at least half the kernel wide
        cl, cs = imgops.label(core)
        big_core = np.zeros(len(cs), bool)
        big_core[1:] = (cs[1:, 2] >= k // 2) & (cs[1:, 3] >= k // 2)
        core = big_core[cl]
    if core.any():
        solid = imgops.dilate(core, k + 2, k + 2) & m
        removed |= solid
        m = m & ~solid

    # 3. components: dark areas cut off by the image border, and isolated specks
    labels, stats = imgops.label(m)
    n = len(stats) - 1
    if n:
        ink_dark = float(np.median(dark[m])) if dark is not None else None
        area = stats[1:, 4]
        big = area >= max(4 * sw * sw, 0.02 * area.sum())
        drop = np.zeros(n + 1, bool)
        strokes = np.isin(labels, np.nonzero(big)[0] + 1) if big.any() else m
        gap = 3 * sw + 4
        near_strokes = imgops.dilate(strokes, 2 * gap + 1, 2 * gap + 1)
        near_ids = set(np.unique(labels[near_strokes & m]).tolist())
        sys, sxs = np.nonzero(strokes)
        sig_box = (sxs.min() - 2 * gap, sys.min() - 2 * gap, sxs.max() + 2 * gap, sys.max() + 2 * gap) if len(sxs) else None
        for idx in range(n):
            x, y, bw, bh, a = stats[idx + 1]
            touches = x == 0 or y == 0 or x + bw >= w or y + bh >= h
            fill = a / max(1, bw * bh)
            along = max(bw / w if (y == 0 or y + bh >= h) else 0, bh / h if (x == 0 or x + bw >= w) else 0)
            if touches and along > 0.3 and fill > 0.25:
                drop[idx + 1] = True
                continue
            if not big[idx]:
                # small piece: keep it close to a stroke, or (i-dots, accents) inside the
                # signature's area when it is stroke-sized and as dark as the ink
                inside = sig_box is not None and sig_box[0] <= x and x + bw <= sig_box[2] and \
                    sig_box[1] <= y and y + bh <= sig_box[3]
                as_dark = ink_dark is None or float(np.median(dark[labels == idx + 1])) >= 0.8 * ink_dark
                keep_it = as_dark and (((idx + 1) in near_ids and a >= max(4, sw * sw // 2)) or
                                       (inside and a >= sw * sw))
                if not keep_it:
                    drop[idx + 1] = True
        gone = drop[labels]
        removed |= gone
        m = m & ~gone

    # keep the soft anti-aliased edge around what survived, nothing else
    keep = imgops.dilate(m, 3, 3) & ~(removed & ~imgops.dilate(m, 3, 3))
    return np.where(keep, alpha, 0).astype(alpha.dtype)
