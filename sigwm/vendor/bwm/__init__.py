"""Embedding core of guofei9987/blind_watermark 0.4.4 (MIT, see LICENSE), rewritten in numpy.

Why not depend on the PyPI package:
- the algorithm must never change between embed and extract, so it is pinned here;
- upstream needs OpenCV (whose wheels bundle ~150 MB of video codecs) and calls
  multiprocessing.set_start_method('fork') at import time, which breaks a frozen
  PySide6 app on macOS;
- upstream prints a banner to stdout on first use.

The math is upstream's: YUV -> Haar DWT -> 4x4 blocks of cA -> DCT -> shuffle ->
SVD -> quantise s0 (step 36) and s1 (step 20). Block loops are vectorised.
tests/test_core.py checks pixel and bit compatibility against upstream, so images
from the old signature_watermark_blind.py script still extract.
"""
from __future__ import annotations

import numpy as np
from numpy.linalg import svd
from pywt import dwt2, idwt2

from ...imgops import bgr_to_yuv, yuv_to_bgr

D1, D2 = 36, 20
# Orthonormal DCT-II matrix; C @ B @ C.T equals cv2.dct(B) for a 4x4 block.
_DCT4 = np.array([[(0.5 if k == 0 else np.sqrt(0.5)) * np.cos(np.pi * (2 * n + 1) * k / 8) for n in range(4)]
                  for k in range(4)])


def str_to_bits(text: str) -> np.ndarray:
    """Same conversion as WaterMark.read_wm(mode='str'), before shuffling."""
    byte = bin(int(text.encode("utf-8").hex(), base=16))[2:]
    return np.array(list(byte)) == "1"


def bits_to_str(bits: np.ndarray) -> str:
    byte = "".join(str(int(b)) for b in bits)
    try:
        return bytes.fromhex(hex(int(byte, base=2))[2:]).decode("utf-8", errors="replace")
    except ValueError:
        return ""


def _shuffle_idx(seed: int, size: int) -> np.ndarray:
    return np.random.RandomState(seed).random(size=(size, 16)).argsort(axis=1)


def capacity_bits(width: int, height: int) -> int:
    return (((height + 1) // 2) // 4) * (((width + 1) // 2) // 4)


class _Core:
    def __init__(self, password_img: int):
        self.password_img = password_img

    def read(self, bgr: np.ndarray):
        self.alpha = None
        if bgr.ndim == 3 and bgr.shape[2] == 4:
            if bgr[:, :, 3].min() < 255:
                self.alpha = bgr[:, :, 3]
            bgr = bgr[:, :, :3]
        h, w = bgr.shape[:2]
        self.img_shape = (h, w)
        yuv = bgr_to_yuv(bgr.astype(np.float32))
        yuv = np.pad(yuv, ((0, h % 2), (0, w % 2), (0, 0)))
        self.ca_shape = ((h + 1) // 2, (w + 1) // 2)
        self.bh, self.bw = self.ca_shape[0] // 4, self.ca_shape[1] // 4
        self.block_num = self.bh * self.bw
        self.ca, self.hvd = [], []
        for ch in range(3):
            ca, hvd = dwt2(yuv[:, :, ch], "haar")
            self.ca.append(ca.astype(np.float32))
            self.hvd.append(hvd)

    def _blocks(self, ch: int) -> np.ndarray:
        """(block_num, 4, 4) in row-major block order, like upstream's block_index."""
        part = self.ca[ch][:self.bh * 4, :self.bw * 4]
        return part.reshape(self.bh, 4, self.bw, 4).transpose(0, 2, 1, 3).reshape(-1, 4, 4)

    def embed(self, wm_bit: np.ndarray) -> np.ndarray:
        wm_size = wm_bit.size
        if wm_size >= self.block_num:
            raise ValueError(f"watermark ({wm_size} bit) does not fit capacity ({self.block_num} bit)")
        shuf = _shuffle_idx(self.password_img, self.block_num)
        unshuf = np.argsort(shuf, axis=1)
        bits = wm_bit[np.arange(self.block_num) % wm_size].astype(np.float64)
        out_yuv = []
        for ch in range(3):
            blocks = self._blocks(ch).astype(np.float64)
            coef = (_DCT4 @ blocks @ _DCT4.T).reshape(-1, 16)
            m = np.take_along_axis(coef, shuf, axis=1).reshape(-1, 4, 4).astype(np.float32)
            u, s, vh = svd(m)
            s = s.astype(np.float64)
            s[:, 0] = (s[:, 0] // D1 + 0.25 + 0.5 * bits) * D1
            s[:, 1] = (s[:, 1] // D2 + 0.25 + 0.5 * bits) * D2
            rec = (u * s[:, None, :]) @ vh
            rec = np.take_along_axis(rec.reshape(-1, 16), unshuf, axis=1).reshape(-1, 4, 4)
            new_blocks = _DCT4.T @ rec @ _DCT4
            ca = self.ca[ch].astype(np.float64).copy()
            ca[:self.bh * 4, :self.bw * 4] = new_blocks.reshape(self.bh, self.bw, 4, 4).transpose(0, 2, 1, 3).reshape(self.bh * 4, self.bw * 4)
            out_yuv.append(idwt2((ca.astype(np.float32), self.hvd[ch]), "haar"))
        yuv = np.stack(out_yuv, axis=2)[:self.img_shape[0], :self.img_shape[1]]
        out = np.clip(yuv_to_bgr(yuv), 0, 255)
        if self.alpha is not None:
            return np.dstack([out.astype(np.uint8), self.alpha])
        return out

    def extract_avg(self, wm_size: int) -> np.ndarray:
        if wm_size >= self.block_num:
            raise ValueError("image too small to hold the watermark")
        shuf = _shuffle_idx(self.password_img, self.block_num)
        bits = np.zeros((3, self.block_num))
        for ch in range(3):
            blocks = self._blocks(ch).astype(np.float64)
            coef = (_DCT4 @ blocks @ _DCT4.T).reshape(-1, 16)
            s = svd(np.take_along_axis(coef, shuf, axis=1).reshape(-1, 4, 4), compute_uv=False)
            bits[ch] = ((s[:, 0] % D1 > D1 / 2) * 3 + (s[:, 1] % D2 > D2 / 2)) / 4
        return np.array([bits[:, i::wm_size].mean() for i in range(wm_size)])


def _kmeans_1d(inputs: np.ndarray) -> np.ndarray:
    center = [inputs.min(), inputs.max()]
    threshold = 0.0
    for _ in range(300):
        threshold = (center[0] + center[1]) / 2
        cls = inputs > threshold
        if cls.all() or (~cls).all():
            break
        center = [inputs[~cls].mean(), inputs[cls].mean()]
        if abs((center[0] + center[1]) / 2 - threshold) < 1e-6:
            threshold = (center[0] + center[1]) / 2
            break
    return inputs > threshold


def embed(img: np.ndarray, text: str, password_img: int, password_wm: int) -> tuple[np.ndarray, int]:
    """img: BGR or BGRA uint8. Returns (watermarked image, wm bit length).
    Float BGR output when the input has no transparency (like upstream)."""
    wm_bit = str_to_bits(text)
    np.random.RandomState(password_wm).shuffle(wm_bit)
    core = _Core(password_img)
    core.read(img)
    return core.embed(wm_bit), wm_bit.size


def extract_bits(img: np.ndarray, wm_size: int, password_img: int, password_wm: int) -> np.ndarray:
    """img: BGR uint8 (alpha ignored). Returns the de-shuffled watermark bits (bool)."""
    if img.ndim == 2:
        img = np.repeat(img[:, :, None], 3, axis=2)
    core = _Core(password_img)
    core.read(img[:, :, :3])
    bits = _kmeans_1d(core.extract_avg(wm_size))
    idx = np.arange(wm_size)
    np.random.RandomState(password_wm).shuffle(idx)
    out = np.empty_like(bits)
    out[idx] = bits
    return out


def extract_str(img: np.ndarray, wm_size: int, password_img: int, password_wm: int) -> str:
    return bits_to_str(extract_bits(img, wm_size, password_img, password_wm))
