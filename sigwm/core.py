"""Signature carrier + blind watermark: embedding, extraction and verification.

Ported from signature_watermark_blind.py; seeds, carrier geometry and the
63-bit short ID are unchanged, so images made by the old script still extract.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from . import background, imgops
from .vendor import bwm
from .i18n import tr

MODES = ("white", "translucent", "feathered", "feathered_texture")
WM_SHAPE = 63  # "W" + 7 uppercase hex chars always encodes to 63 bits
MIN_CARRIER = (320, 192)


class WatermarkError(Exception):
    """Raised with a message that can be shown to the user as-is."""


class SelfCheckError(WatermarkError):
    """The freshly embedded image did not read back; a new ID usually fixes it."""


@dataclass
class CarrierParams:
    mode: str = "feathered_texture"
    padding: int = 64
    alpha: int = 96
    feather: int = 48
    texture: int = 4
    remove_background: bool = True
    background_threshold: int = 220

    def validate(self):
        if self.mode not in MODES:
            raise WatermarkError(tr('未知的載體模式：{mode}', mode=self.mode))
        for name, lo, hi in (("padding", 16, 300), ("alpha", 16, 255), ("feather", 4, 250), ("texture", 0, 20),
                             ("background_threshold", 100, 250)):
            v = getattr(self, name)
            if not lo <= v <= hi:
                raise WatermarkError(tr('{name} 必須在 {lo} 到 {hi} 之間', name=name, lo=lo, hi=hi))


@dataclass
class EmbedResult:
    short_id: str
    image: Image.Image          # RGBA, watermarked
    width: int
    height: int
    sig_bbox: tuple[int, int, int, int]  # visible signature inside the carrier
    capacity: int
    warnings: list[str] = field(default_factory=list)


def password_seeds(password: str) -> tuple[int, int]:
    if len(password) < 12:
        raise WatermarkError(tr('水印密碼至少需要 12 個字元'))
    img_digest = hashlib.sha256(("img:" + password).encode("utf-8")).digest()
    wm_digest = hashlib.sha256(("wm:" + password).encode("utf-8")).digest()
    return int.from_bytes(img_digest[:4], "big"), int.from_bytes(wm_digest[:4], "big")


def new_short_id() -> str:
    return "W" + secrets.token_hex(4).upper()[:7]


def short_id_bits(short_id: str) -> np.ndarray:
    return bwm.str_to_bits(short_id)


def capacity_bits(width: int, height: int) -> int:
    return bwm.capacity_bits(width, height)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


# ---------------------------------------------------------------- carrier

def load_signature(path: Path) -> tuple[Image.Image, list[str]]:
    """Open and orient an image as RGBA; preparation is shared by preview and embedding."""
    warnings: list[str] = []
    try:
        img = Image.open(path)
        img.load()
        img = ImageOps.exif_transpose(img)
    except Exception as exc:  # noqa: BLE001 - Pillow raises many types
        raise WatermarkError(tr('無法讀取圖片：{exc}', exc=exc)) from exc
    img = img.convert("RGBA")
    return img, warnings


def prepare_signature(img: Image.Image, p: CarrierParams) -> Image.Image:
    """Remove opaque paper before cropping/adding a replacement carrier."""
    img = img.convert("RGBA")
    if p.remove_background and background.has_paper_background(img):
        img = background.remove_paper(img, p.background_threshold)
        if img.getchannel("A").getbbox() is None:
            raise WatermarkError(tr('未檢測到筆跡，請提高筆跡保留閾值或關閉自動去背景'))
    return img


def prepare_master(img: Image.Image, padding: int) -> tuple[Image.Image, tuple[int, int, int, int]]:
    bbox = img.getchannel("A").getbbox()
    if bbox is None:
        raise WatermarkError(tr('圖片沒有可見像素'))
    l, t, r, b = bbox
    cropped = img.crop(bbox)
    tw = max(cropped.width + padding * 2, MIN_CARRIER[0])
    th = max(cropped.height + padding * 2, MIN_CARRIER[1])
    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    x, y = (tw - cropped.width) // 2, (th - cropped.height) // 2
    canvas.alpha_composite(cropped, (x, y))
    return canvas, (x, y, x + cropped.width, y + cropped.height)


def feather_mask(width: int, height: int, alpha_max: int, feather: int) -> np.ndarray:
    y, x = np.mgrid[0:height, 0:width]
    d = np.minimum(np.minimum(x, width - 1 - x), np.minimum(y, height - 1 - y)).astype(np.float32)
    u = np.clip(d / max(1, feather), 0.0, 1.0)
    u = u * u * (3.0 - 2.0 * u)
    return np.round(u * alpha_max).astype(np.uint8)


def build_carrier(master: Image.Image, p: CarrierParams, texture_seed: int) -> Image.Image:
    w, h = master.size
    if p.mode == "white":
        # 250, not 255: pure white leaves the DCT/SVD quantiser no headroom and
        # flips bits after clipping (upstream fails its own round-trip there).
        rgb = np.full((h, w, 3), 250, dtype=np.uint8)
        alpha = np.full((h, w), 255, dtype=np.uint8)
    elif p.mode == "translucent":
        rgb = np.full((h, w, 3), 255, dtype=np.uint8)
        alpha = np.full((h, w), p.alpha, dtype=np.uint8)
    else:
        if p.mode == "feathered_texture":
            rng = np.random.default_rng(texture_seed)
            noise = rng.integers(-p.texture, p.texture + 1, size=(h, w, 1), dtype=np.int16)
            rgb = np.clip(np.full((h, w, 3), 250, dtype=np.int16) + noise, 0, 255).astype(np.uint8)
        else:
            rgb = np.full((h, w, 3), 255, dtype=np.uint8)
        alpha = feather_mask(w, h, p.alpha, p.feather)
    carrier = Image.fromarray(np.dstack((rgb, alpha)), mode="RGBA")
    carrier.alpha_composite(master)
    return carrier


def render_preview(img: Image.Image, p: CarrierParams, seed: int = 1) -> Image.Image:
    """Carrier preview without the (slow) watermark step."""
    master, _ = prepare_master(prepare_signature(img, p), p.padding)
    return build_carrier(master, p, seed)


# ---------------------------------------------------------------- embed / extract

APPEARANCE_CAP = 250  # flattened-on-white ceiling; leaves the quantiser headroom below 255
FORMAT = "SIG-BLIND-WM-2"


def flatten_on_white(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    return Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba).convert("RGB")


def _embed_appearance(carrier: Image.Image, short_id: str, seed_img: int, seed_wm: int) -> Image.Image:
    """Embed into what the carrier looks like on white paper, then solve back for RGB.

    The old script embedded into the raw RGB of a semi-transparent carrier, so the
    signal was scaled down by alpha once the PNG was placed on a page and rarely
    survived. Embedding in the flattened appearance keeps the full signal visible:
    on a white page the composite equals the watermarked image exactly.
    """
    rgba = np.asarray(carrier.convert("RGBA"))
    a = rgba[:, :, 3:4].astype(np.float64) / 255.0
    rgb = rgba[:, :, :3].astype(np.float64)
    flat = np.minimum(255.0 * (1 - a) + rgb * a, APPEARANCE_CAP)
    bgr = np.ascontiguousarray(np.round(flat).astype(np.uint8)[:, :, ::-1])
    out, wm_size = bwm.embed(bgr, short_id, seed_img, seed_wm)
    if wm_size != WM_SHAPE:
        raise WatermarkError(tr('內部錯誤：水印長度 {wm_size}', wm_size=wm_size))
    target = np.clip(np.round(out[:, :, :3]), 0, 255).astype(np.uint8)[:, :, ::-1].astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        solved = np.where(a > 0, (target - 255.0 * (1 - a)) / a, rgb)
    solved = np.clip(np.round(solved), 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([solved, rgba[:, :, 3]]), mode="RGBA")


def embed_signature(img: Image.Image, password: str, p: CarrierParams, sig_id_for_seed: str,
                    short_id: str, self_check: bool = True) -> EmbedResult:
    p.validate()
    seed_img, seed_wm = password_seeds(password)
    master, sig_bbox = prepare_master(prepare_signature(img, p), p.padding)
    texture_seed = int(hashlib.sha256(sig_id_for_seed.encode("ascii")).hexdigest()[:8], 16)
    carrier = build_carrier(master, p, texture_seed)
    cap = capacity_bits(*carrier.size)
    if cap <= WM_SHAPE:
        raise WatermarkError(tr('載體太小：容量 {cap} bit，水印需要 {WM_SHAPE} bit。請加大四周留白', cap=cap, WM_SHAPE=WM_SHAPE))

    result = _embed_appearance(carrier, short_id, seed_img, seed_wm)
    if not np.array_equal(np.asarray(carrier.getchannel("A")), np.asarray(result.getchannel("A"))):
        raise WatermarkError(tr('透明通道校驗失敗：輸出的透明度和預期不同'))
    if self_check:
        got = extract(result, password).text
        if got != short_id:
            raise SelfCheckError(tr('回提自檢失敗：提取到 {got!r}', got=got))
    return EmbedResult(short_id, result, carrier.width, carrier.height, sig_bbox, cap)


@dataclass
class ExtractResult:
    text: str
    bits: np.ndarray
    resized: bool


def _to_bgr(img: Image.Image | np.ndarray, flatten: bool) -> np.ndarray:
    if isinstance(img, np.ndarray):
        if img.ndim == 2:
            return np.repeat(img[:, :, None], 3, axis=2)
        return img[:, :, :3]
    if flatten:
        img = flatten_on_white(img)
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    return np.ascontiguousarray(np.asarray(img)[:, :, 2::-1])


def _has_alpha(img) -> bool:
    return isinstance(img, Image.Image) and (img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info)


def _extract_bgr(bgr: np.ndarray, seed_img: int, seed_wm: int, size) -> ExtractResult:
    resized = False
    if size and (bgr.shape[1], bgr.shape[0]) != tuple(size):
        bgr = imgops.resize(bgr, tuple(size))
        resized = True
    if capacity_bits(bgr.shape[1], bgr.shape[0]) <= WM_SHAPE:
        raise WatermarkError(tr('圖片太小，無法提取水印'))
    bits = bwm.extract_bits(bgr, WM_SHAPE, seed_img, seed_wm)
    return ExtractResult(bwm.bits_to_str(bits), bits, resized)


def extract(img: Image.Image | np.ndarray, password: str, size: tuple[int, int] | None = None) -> ExtractResult:
    """Extract the short ID. If `size` (w, h) is known and differs, resize back first.

    Transparent PNGs are read as they look on white paper (current format). Images
    from the old script carry the mark in raw RGB, so `extract_candidates` also
    tries that for transparent input.
    """
    seed_img, seed_wm = password_seeds(password)
    return _extract_bgr(_to_bgr(img, flatten=True), seed_img, seed_wm, size)


def extract_candidates(img: Image.Image | np.ndarray, password: str,
                       size: tuple[int, int] | None = None) -> list[ExtractResult]:
    seed_img, seed_wm = password_seeds(password)
    out = [_extract_bgr(_to_bgr(img, flatten=True), seed_img, seed_wm, size)]
    if _has_alpha(img):
        out.append(_extract_bgr(_to_bgr(img, flatten=False), seed_img, seed_wm, size))
    return out


def bit_agreement(bits: np.ndarray, short_id: str) -> int:
    ref = short_id_bits(short_id)
    if ref.size != bits.size:
        return 0
    return int((ref == bits).sum())


# ---------------------------------------------------------------- robustness self-test

def robustness_test(watermarked: Image.Image, password: str, short_id: str) -> list[tuple[str, bool, str]]:
    size = watermarked.size
    flat = Image.alpha_composite(Image.new("RGBA", size, (255, 255, 255, 255)), watermarked.convert("RGBA")).convert("RGB")
    cases: list[tuple[str, Image.Image]] = [(tr('合成到白底'), flat)]
    for pct in (75, 50):
        cases.append((tr('縮小到 {pct}%', pct=pct), flat.resize((max(1, size[0] * pct // 100), max(1, size[1] * pct // 100)), Image.Resampling.LANCZOS)))
    import io
    buf = io.BytesIO()
    flat.save(buf, "JPEG", quality=90)
    buf.seek(0)
    cases.append((tr('JPEG 質量 90'), Image.open(buf)))
    out = []
    for label, im in cases:
        try:
            got = extract(im, password, size).text
            out.append((label, got == short_id, got))
        except WatermarkError as exc:
            out.append((label, False, str(exc)))
    return out
