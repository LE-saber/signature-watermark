"""Find signatures in documents, photos and scans, and match them to signing records.

Pipeline per input:
1. collect candidate images
   - PDF: every embedded image (exact pixels, with soft mask) + the rendered page
   - DOCX: every image in word/media
   - image file: the image itself
2. direct attempt: read the candidate as-is (or resized back to a record's size
   when the aspect ratio matches). This covers signatures pasted into documents.
3. locate attempt for large images (scans, photos, screenshots, rendered pages):
   find ink blobs, and for each record map the blob onto that record's carrier
   using the stored signature bbox, then extract. Small offset/scale jitter is
   tried when a record comes close.
4. compare extracted bits with every record (bit agreement out of 63).
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from . import core, imgops
from .storage import Record, Store
from .i18n import tr

# Bits that differ between IDs. "W" and the high nibble pattern of each hex
# character are the same in every ID, so they say a mark is present but not whose.
_HEX = "0123456789ABCDEF"
_ALL = np.array([core.short_id_bits("W" + c * 7) for c in _HEX])
VAR_MASK = _ALL.std(axis=0) > 0
N_VAR, N_FIXED = int(VAR_MASK.sum()), int((~VAR_MASK).sum())   # 49, 14

# Thresholds on agreement over the 49 variable bits, calibrated against images that
# carry a *different* ID (the worst case: a clean mark that is not in the records)
# searched over many records and alignments. See tests/test_trace.py.
MATCH_VAR = 46
WEAK_VAR = 43
WEAK_MARGIN = 5     # weak needs a clear lead over the runner-up record
PREVIEW_W = 900

Progress = Callable[[str], None]


@dataclass
class Hit:
    page: int                          # 1-based
    box: tuple[int, int, int, int]     # in page preview pixels (x0, y0, x1, y1)
    kind: str                          # match | weak | none
    record: Record | None = None
    bits: int = 0                      # agreement over all 63 bits, for display
    note: str = ""
    crop: Image.Image | None = None


@dataclass
class Page:
    preview: Image.Image
    scale: float                       # preview px per source px


@dataclass
class TraceResult:
    path: Path
    kind: str                          # PDF | DOCX | IMAGE
    pages: list[Page] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    error: str = ""


@dataclass
class Score:
    record: Record | None = None
    var: int = 0          # agreement on the 49 variable bits
    total: int = 0        # agreement on all 63 bits
    runner_up: int = 0    # var agreement of the second-best record
    exact: bool = False   # decoded string equals the record's ID

    def better(self, other: "Score") -> bool:
        return (self.exact, self.var) > (other.exact, other.var)


class _Matcher:
    """Compares extracted bits with all records in one vectorised step."""

    def __init__(self, records: list[Record], password: str):
        self.records = [r for r in records if r.wm_shape == core.WM_SHAPE]
        self.password = password
        self.ref = np.array([core.short_id_bits(r.short_id) for r in self.records]) if self.records else np.zeros((0, 63), bool)
        sizes: dict[tuple[int, int], list[int]] = {}
        for i, r in enumerate(self.records):
            sizes.setdefault((r.width, r.height), []).append(i)
        self.sizes = sizes
        self._alpha: dict[int, np.ndarray | None] = {}
        self._ink: dict[int, np.ndarray | None] = {}

    def best(self, bits: np.ndarray, text: str, among: list[int] | None = None) -> Score:
        if not len(self.records):
            return Score()
        idx = np.array(among if among is not None else range(len(self.records)))
        eq = self.ref[idx] == bits[None, :]
        var = eq[:, VAR_MASK].sum(axis=1)
        order = np.argsort(-var)
        k = int(order[0])
        rec = self.records[int(idx[k])]
        # runner-up over all records, so a lead is judged against the whole set
        all_var = (self.ref[:, VAR_MASK] == bits[None, VAR_MASK]).sum(axis=1)
        all_var[int(idx[k])] = -1
        runner = int(all_var.max()) if len(all_var) > 1 else 24
        return Score(rec, int(var[k]), int(eq[k].sum()), max(runner, 24), text == rec.short_id)

    def alpha_map(self, i: int) -> np.ndarray | None:
        """Carrier opacity for record i, rebuilt from its stored parameters (None: opaque or unknown)."""
        if i not in self._alpha:
            r = self.records[i]
            p = r.params or {}
            a = None
            if r.format != "SIG-BLIND-WM-1" and "alpha" in p and r.width and r.height:
                try:
                    a = core.carrier_alpha(r.mode, r.width, r.height, int(p["alpha"]), int(p.get("feather", 48)))
                except (TypeError, ValueError):
                    a = None
            self._alpha[i] = a
        return self._alpha[i]

    def try_on_paper(self, bgr: np.ndarray, i: int, paper: np.ndarray | None) -> Score:
        """bgr is already at record i's size. Also try it corrected for tinted paper."""
        best = self.try_image(bgr, None, [i])
        a = self.alpha_map(i)
        if a is None or a.shape != bgr.shape[:2] or _classify(best) == "match":
            return best
        if paper is None:
            paper = core.paper_from_ring(bgr, a)
        if core.paper_is_white(paper):
            return best
        s2 = self.try_image(core.correct_paper(bgr, a, paper), None, [i])
        return s2 if s2.better(best) else best

    def try_image(self, img: Image.Image | np.ndarray, size=None, among=None) -> Score:
        best = Score()
        try:
            for res in core.extract_candidates(img, self.password, size):
                cand = self.best(res.bits, res.text, among)
                if cand.better(best):
                    best = cand
        except core.WatermarkError:
            pass
        return best


def _classify(s: Score) -> str:
    if s.record is None:
        return "none"
    if s.exact or s.var >= MATCH_VAR:
        return "match"
    if s.var >= WEAK_VAR and s.var - s.runner_up >= WEAK_MARGIN:
        return "weak"
    return "none"


def _direct(m: _Matcher, img: Image.Image) -> tuple[Score, bool]:
    """Try the image as a whole signature carrier: as-is, then resized to records of matching aspect."""
    best = m.try_image(img)
    resized = False
    if _classify(best) == "match":
        return best, False
    w, h = img.size
    if w < 40 or h < 24:
        return best, False
    opaque = img.mode not in ("RGBA", "LA", "PA") and "transparency" not in img.info
    bgr0 = core._to_bgr(img, flatten=True) if opaque else None
    for (rw, rh), idx in m.sizes.items():
        if abs((w / h) / (rw / rh) - 1) > 0.03:
            continue
        if (rw, rh) != (w, h):
            s2 = m.try_image(img, (rw, rh), idx)
            if s2.better(best):
                best, resized = s2, True
        if opaque and _classify(best) != "match":
            # a screenshot or photo of the carrier on tinted paper
            bgr = imgops.resize(bgr0, (rw, rh))
            for i in idx:
                s3 = m.try_on_paper(bgr, i, None)
                if s3.better(best):
                    best, resized = s3, (rw, rh) != (w, h)
        if _classify(best) == "match":
            break
    return best, resized


def ink_mask(bgr: np.ndarray) -> np.ndarray:
    """Pixels darker than their surroundings: handwriting, printed text, lines."""
    gray = imgops.gray(bgr)
    h, w = gray.shape
    k = max(15, (min(h, w) // 40) | 1)
    # adaptive threshold: darker than the local mean by more than 18 levels
    ink = gray < imgops.box_mean(imgops.box_mean(gray, 3), k) - 18
    return imgops.dilate(imgops.erode(ink, 2, 2), 2, 2)          # opening removes specks


def ink_blobs(bgr: np.ndarray, max_blobs: int = 8, ink: np.ndarray | None = None) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of handwriting-like ink regions, largest first."""
    if ink is None:
        ink = ink_mask(bgr)
    h, w = ink.shape
    kx, ky = max(5, w // 60), max(3, h // 120)
    merged = imgops.dilate(ink, ky, kx)
    boxes = []
    for x, y, bw, bh, area in imgops.label_boxes(merged):
        if bw < w * 0.04 or bh < 8 or bw > w * 0.95:
            continue
        aspect = bw / max(1, bh)
        if aspect > 12 or aspect < 0.8:
            continue
        # shrink back to the real ink extent inside the merged blob
        sub = ink[y:y + bh, x:x + bw]
        ys, xs = np.nonzero(sub)
        if len(xs) < 30:
            continue
        boxes.append((x + xs.min(), y + ys.min(), x + xs.max() + 1, y + ys.max() + 1))
    if len(boxes) > 3:
        hs = np.median([b[3] - b[1] for b in boxes])
        tall = [b for b in boxes if (b[3] - b[1]) >= 1.6 * hs]
        boxes = tall or boxes
    boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    return boxes[:max_blobs]


def _crop_padded(bgr: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    h, w = bgr.shape[:2]
    X0, Y0, X1, Y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    out = np.full((max(1, Y1 - Y0), max(1, X1 - X0), 3), 255, np.uint8)
    sx0, sy0, sx1, sy1 = max(0, X0), max(0, Y0), min(w, X1), min(h, Y1)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0 - Y0:sy1 - Y0, sx0 - X0:sx1 - X0] = bgr[sy0:sy1, sx0:sx1]
    return out


def _record_ink(m: _Matcher, i: int) -> np.ndarray | None:
    """Ink shape of record i (opaque pixels of its output PNG), cropped to the signature box."""
    if i in m._ink:
        return m._ink[i]
    r, ink = m.records[i], None
    try:
        if r.out_path and r.sig_bbox[2] > r.sig_bbox[0]:
            with Image.open(r.out_path) as im:
                if im.size == (r.width, r.height) and "A" in im.getbands():
                    a = np.asarray(im.getchannel("A"))
                    x0, y0, x1, y1 = r.sig_bbox
                    ink = a[y0:y1, x0:x1] >= 250
                    if ink.sum() < 50:
                        ink = None
    except OSError:
        ink = None
    m._ink[i] = ink
    return ink


def find_by_shape(m: _Matcher, ink: np.ndarray, limit_px: int = 700) -> list[tuple[float, int, tuple[int, int, int, int]]]:
    """Find each record's signature on a page by matching its ink shape.

    Works when the signature touches printed text, where connected-ink blobs merge
    the two. Multi-scale normalised cross-correlation via FFT on a reduced page.
    Returns (score, record index, ink box in page pixels), best first.
    """
    h, w = ink.shape
    f = min(1.0, limit_px / max(h, w))
    small = np.asarray(Image.fromarray(ink.astype(np.uint8) * 255).resize(
        (max(1, int(w * f)), max(1, int(h * f))), Image.Resampling.BOX), dtype=np.float64) / 255
    small = imgops.box_mean(small, 3)          # tolerate the gap between scale steps
    H, W = small.shape
    page_f = np.fft.rfft2(small)
    out = []
    for i in range(len(m.records)):
        tmpl = _record_ink(m, i)
        if tmpl is None:
            continue
        th0, tw0 = tmpl.shape
        best = (0.0, None)
        # a tiny template fits inside any letter, so start at a plausible signature width
        scale = max(40 / tw0, 0.08 * W / tw0)
        while tw0 * scale <= 0.95 * W and th0 * scale <= 0.95 * H:
            tw, th = max(4, int(round(tw0 * scale))), max(4, int(round(th0 * scale)))
            t = np.asarray(Image.fromarray(tmpl.astype(np.uint8) * 255).resize((tw, th), Image.Resampling.BOX),
                           dtype=np.float64) / 255
            t = imgops.box_mean(t, 3)
            t_sum = float(t.sum())
            if t_sum > 1:
                pad = np.zeros_like(small)
                pad[:th, :tw] = t
                corr = np.fft.irfft2(page_f * np.conj(np.fft.rfft2(pad)), s=small.shape)
                density = imgops.box_sum(small, th, tw) / (th * tw)      # ink density under the window
                # box_sum is centred; shift so it lines up with the top-left anchor of corr
                density = np.roll(np.roll(density, -(th // 2), axis=0), -(tw // 2), axis=1)
                # share of the template's ink found there, minus what dense text would give by chance
                score = corr / t_sum - density
                score[H - th + 1:, :] = 0
                score[:, W - tw + 1:] = 0
                k = int(score.argmax())
                y, x = divmod(k, W)
                if score.flat[k] > best[0]:
                    best = (float(score.flat[k]), (x / f, y / f, (x + tw) / f, (y + th) / f))
            scale *= 1.07
        if best[1] is not None:
            out.append((best[0], i, tuple(int(round(v)) for v in best[1])))
    out.sort(reverse=True)
    return out


def refine_by_shape(m: _Matcher, ink: np.ndarray, i: int, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Full-resolution shape match around a coarse box (+-30 px, scale +-4 %)."""
    tmpl = _record_ink(m, i)
    if tmpl is None:
        return box
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    margin = max(30, int(0.04 * bw))
    H, W = ink.shape
    X0, Y0 = max(0, x0 - margin), max(0, y0 - margin)
    X1, Y1 = min(W, x1 + 2 * margin), min(H, y1 + 2 * margin)
    region = imgops.box_mean(ink[Y0:Y1, X0:X1].astype(np.float64), 3)
    rh, rw = region.shape
    reg_f = np.fft.rfft2(region)
    best = (-1.0, box)
    for ds in np.linspace(0.96, 1.04, 9):
        tw, th = int(round(bw * ds)), int(round(bh * ds))
        if tw < 8 or th < 8 or tw >= rw or th >= rh:
            continue
        t = np.asarray(Image.fromarray(tmpl.astype(np.uint8) * 255).resize((tw, th), Image.Resampling.BOX),
                       dtype=np.float64) / 255
        t = imgops.box_mean(t, 3)
        pad = np.zeros_like(region)
        pad[:th, :tw] = t
        corr = np.fft.irfft2(reg_f * np.conj(np.fft.rfft2(pad)), s=region.shape) / max(t.sum(), 1e-6)
        corr[rh - th + 1:, :] = -1
        corr[:, rw - tw + 1:] = -1
        k = int(corr.argmax())
        y, x = divmod(k, rw)
        if corr.flat[k] > best[0]:
            best = (float(corr.flat[k]), (X0 + x, Y0 + y, X0 + x + tw, Y0 + y + th))
    return best[1]


def locate(m: _Matcher, bgr: np.ndarray, box: tuple[int, int, int, int],
           only: list[int] | None = None) -> tuple[Score, tuple]:
    """Map an ink box onto each record's carrier geometry and extract.

    The mark lives in 8x8-pixel blocks of the carrier, so a 1-2 px misalignment
    already costs many bits. When a record comes close, search offsets around the
    estimate (coarse 2 px grid, then 1 px) and a little scale.
    """
    bx0, by0, bx1, by1 = box
    bw, bh = bx1 - bx0, by1 - by0
    best, best_box = Score(), box

    paper: dict[int, np.ndarray | None] = {}

    def attempt(i, r, s, dx, dy):
        cx0 = bx0 - r.sig_bbox[0] * s + dx * s
        cy0 = by0 - r.sig_bbox[1] * s + dy * s
        cbox = (cx0, cy0, cx0 + r.width * s, cy0 + r.height * s)
        crop = imgops.resize(_crop_padded(bgr, *cbox), (r.width, r.height))
        if i not in paper:
            # paper colour from the page just outside the carrier
            paper[i] = core.paper_from_surroundings(bgr, cbox, 0.06 * r.width * s)
        return m.try_on_paper(crop, i, paper[i]), tuple(int(v) for v in cbox)

    for i, r in enumerate(m.records):
        if only is not None and i not in only:
            continue
        sx0, sy0, sx1, sy1 = r.sig_bbox
        sw, sh = sx1 - sx0, sy1 - sy0
        if sw <= 0 or sh <= 0 or abs((bw / bh) / (sw / sh) - 1) > 0.25:
            continue
        s0 = (bw + bh) / (sw + sh)
        sc, cbox = attempt(i, r, s0, 0, 0)
        cur = (sc, 0.0, 0.0, s0, cbox)
        if WEAK_VAR - 12 <= sc.var < MATCH_VAR and not sc.exact:
            for grid in ((-4, -2, 0, 2, 4), (-1, 0, 1)):
                bx, by, bs = cur[1], cur[2], cur[3]
                for ds in ((1.0,) if len(grid) == 3 else (0.995, 1.0, 1.005)):
                    for dx in grid:
                        for dy in grid:
                            if dx == dy == 0 and ds == 1.0:
                                continue
                            s2, c2 = attempt(i, r, bs * ds, bx + dx, by + dy)
                            if s2.better(cur[0]):
                                cur = (s2, bx + dx, by + dy, bs * ds, c2)
                if _classify(cur[0]) == "match":
                    break
        if cur[0].better(best):
            best, best_box = cur[0], cur[4]
        if _classify(best) == "match":
            break
    return best, best_box


def _preview(img: Image.Image) -> Page:
    img = img.convert("RGB")
    scale = min(1.0, PREVIEW_W / img.width)
    if scale < 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    return Page(img, scale)


def _scan_large(m: _Matcher, img: Image.Image, page_no: int, page: Page, offset=(0, 0), src_scale=1.0,
                progress: Progress | None = None) -> list[Hit]:
    """Locate signatures inside a big image (scan / photo / rendered page)."""
    bgr = np.ascontiguousarray(np.asarray(core.flatten_on_white(img))[:, :, ::-1])
    ink = ink_mask(bgr)
    k = page.scale * src_scale

    def make_hit(box, sc, cbox):
        kind = _classify(sc)
        pb = tuple(int(v * k + o) for v, o in zip(box, (*offset, *offset)))
        crop = Image.fromarray(np.ascontiguousarray(_crop_padded(bgr, *(cbox if kind != "none" else box))[:, :, ::-1]))
        return Hit(page_no, pb, kind, sc.record if kind != "none" else None, sc.total, crop=crop)

    found = []
    for box in ink_blobs(bgr, ink=ink):
        if progress:
            progress(tr('對比簽發記錄'))
        sc, cbox = locate(m, bgr, box)
        found.append((box, sc, cbox))
    if not any(_classify(sc) == "match" for _, sc, _ in found):
        # a signature touching printed text merges into one blob with it: find it by shape
        if progress:
            progress(tr('按簽名形狀定位'))
        for score, i, box in find_by_shape(m, ink)[:5]:
            if score < 0.12:
                break
            box = refine_by_shape(m, ink, i, box)
            sc, cbox = locate(m, bgr, box, only=[i])
            if _classify(sc) != "none":
                # drop blob results that cover the same place
                found = [f for f in found if not _overlaps(f[0], box)]
                found.append((box, sc, cbox))
                break
    return [make_hit(box, sc, cbox) for box, sc, cbox in found]


def _overlaps(a, b) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _note(hit: Hit, resized: bool = False, located: bool = False) -> str:
    if hit.kind == "match":
        return tr('已按記錄尺寸還原後提取。') if resized else (tr('已按記錄的簽名位置定位並還原後提取。') if located else "")
    if hit.kind == "weak":
        return tr('只有 {bits}/63 位一致，圖片可能被壓縮或縮放得比較厲害，結果只能作參考，建議找原件再查。', bits=hit.bits)
    return tr('沒有找到本工具的水印。可能是別人的簽名、沒經過本工具處理，或者圖片質量太差。')


def analyze_image_region(store: Store, password: str, img: Image.Image, page_no: int = 1,
                         box: tuple[int, int, int, int] | None = None) -> Hit:
    """Manual selection: treat the given region as one signature."""
    m = _Matcher(store.records(), password)
    region = img.crop(box) if box else img
    sc, resized = _direct(m, region)
    if _classify(sc) == "none":
        bgr = np.ascontiguousarray(np.asarray(core.flatten_on_white(region))[:, :, ::-1])
        blobs = ink_blobs(bgr, 1)
        if blobs:
            s2, _ = locate(m, bgr, blobs[0])
            if s2.better(sc):
                sc = s2
    hit = Hit(page_no, box or (0, 0, *img.size), _classify(sc), None, sc.total, crop=region.convert("RGB"))
    hit.record = sc.record if hit.kind != "none" else None
    hit.note = _note(hit, resized)
    return hit


def analyze(store: Store, password: str, path: Path, progress: Progress | None = None) -> TraceResult:
    path = Path(path)
    m = _Matcher(store.records(), password)
    ext = path.suffix.lower()
    say = progress or (lambda _s: None)
    try:
        if ext == ".pdf":
            return _analyze_pdf(m, path, say)
        if ext in (".docx", ".docm"):
            return _analyze_docx(m, path, say)
        return _analyze_image_file(m, path, say)
    except core.WatermarkError as exc:
        return TraceResult(path, ext.lstrip(".").upper(), error=str(exc))
    except Exception as exc:  # noqa: BLE001 - corrupt files from outside; report, don't crash
        return TraceResult(path, ext.lstrip(".").upper(), error=tr('無法讀取這個文件：{exc}', exc=exc))


def _analyze_image_file(m: _Matcher, path: Path, say: Progress) -> TraceResult:
    say(tr('讀取頁面'))
    img = Image.open(path)
    img.load()
    page = _preview(img)
    res = TraceResult(path, "IMAGE", [page])
    say(tr('提取水印'))
    sc, resized = _direct(m, img)
    if _classify(sc) != "none":
        h = Hit(1, (0, 0, *page.preview.size), _classify(sc), sc.record, sc.total, crop=img.convert("RGB"))
        h.note = _note(h, resized)
        res.hits.append(h)
        return res
    say(tr('檢測簽名區域'))
    for h in _scan_large(m, img, 1, page, progress=say):
        h.note = _note(h, located=True)
        res.hits.append(h)
    return res


def _analyze_pdf(m: _Matcher, path: Path, say: Progress) -> TraceResult:
    import pymupdf
    res = TraceResult(path, "PDF")
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            raise core.WatermarkError(tr('PDF 有打開密碼，請先解除密碼再溯源'))
        for pno, page in enumerate(doc, start=1):
            say(tr('讀取第 {pno} 頁', pno=pno))
            zoom = PREVIEW_W / page.rect.width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            prev = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pg = Page(prev, zoom)  # preview px per PDF point
            res.pages.append(pg)
            page_hits: list[Hit] = []
            for info in page.get_images(full=True):
                xref, smask = info[0], info[1]
                try:
                    pm = pymupdf.Pixmap(doc, xref)
                    if smask:
                        pm = pymupdf.Pixmap(pm, pymupdf.Pixmap(doc, smask))
                    if pm.n - pm.alpha >= 4:
                        pm = pymupdf.Pixmap(pymupdf.csRGB, pm)
                    img = Image.open(io.BytesIO(pm.tobytes("png")))
                    img.load()
                except Exception:  # noqa: BLE001 - unusual colour spaces etc.
                    continue
                rects = page.get_image_rects(xref) or [page.rect]
                r = rects[0]
                box = (int(r.x0 * zoom), int(r.y0 * zoom), int(r.x1 * zoom), int(r.y1 * zoom))
                say(tr('提取水印'))
                sc, resized = _direct(m, img)
                if _classify(sc) != "none":
                    h = Hit(pno, box, _classify(sc), sc.record, sc.total, crop=img.convert("RGB"))
                    h.note = _note(h, resized)
                    page_hits.append(h)
                    continue
                cover = (r.width * r.height) / max(1, page.rect.width * page.rect.height)
                if cover > 0.3 and img.width > 600:   # scanned page stored as one image
                    say(tr('檢測簽名區域'))
                    px_per_pt = img.width / max(1, r.width)
                    for h in _scan_large(m, img, pno, Page(prev, zoom), offset=box[:2], src_scale=1 / px_per_pt, progress=say):
                        h.note = _note(h, located=True)
                        page_hits.append(h)
                else:
                    h = Hit(pno, box, "none", None, sc.total, crop=img.convert("RGB"))
                    if img.width >= 120 and img.height >= 60:
                        h.note = _note(h)
                        page_hits.append(h)
            res.hits.extend(page_hits)
    return res


def _analyze_docx(m: _Matcher, path: Path, say: Progress) -> TraceResult:
    res = TraceResult(path, "DOCX")
    say(tr('讀取文件'))
    with zipfile.ZipFile(path) as zf:
        media = [n for n in zf.namelist() if n.startswith("word/media/")]
        for i, name in enumerate(media, start=1):
            try:
                img = Image.open(io.BytesIO(zf.read(name)))
                img.load()
            except Exception:  # noqa: BLE001 - emf/wmf etc.
                continue
            page = _preview(img)
            res.pages.append(page)
            pno = len(res.pages)
            say(tr('提取水印'))
            sc, resized = _direct(m, img)
            if _classify(sc) != "none":
                h = Hit(pno, (0, 0, *page.preview.size), _classify(sc), sc.record, sc.total, crop=img.convert("RGB"))
                h.note = _note(h, resized)
                res.hits.append(h)
            elif img.width > 600:
                for h in _scan_large(m, img, pno, page, progress=say):
                    h.note = _note(h, located=True)
                    res.hits.append(h)
            elif img.width >= 120:
                h = Hit(pno, (0, 0, *page.preview.size), "none", None, sc.total, crop=img.convert("RGB"))
                h.note = _note(h)
                res.hits.append(h)
    return res


def full_page(res: TraceResult, page_no: int) -> tuple[Image.Image, float]:
    """High-resolution image of a page, plus full-res pixels per preview pixel (for manual selection)."""
    page = res.pages[page_no - 1]
    if res.kind == "PDF":
        import pymupdf
        with pymupdf.open(res.path) as doc:
            p = doc[page_no - 1]
            zoom = page.scale * 3
            pix = p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples), 3.0
    if res.kind == "DOCX":
        with zipfile.ZipFile(res.path) as zf:
            media = [n for n in zf.namelist() if n.startswith("word/media/")]
            imgs = []
            for name in media:
                try:
                    im = Image.open(io.BytesIO(zf.read(name)))
                    im.load()
                    imgs.append(im)
                except Exception:  # noqa: BLE001
                    continue
            img = imgs[page_no - 1]
            return img, 1 / page.scale
    img = Image.open(res.path)
    img.load()
    return img, 1 / page.scale
