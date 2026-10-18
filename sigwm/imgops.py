"""The few image operations the app needs, in numpy + Pillow.

OpenCV was only used for these, yet its wheels bundle ffmpeg, libaom, libvpx and
OpenBLAS (~150 MB in the frozen app). Formulas that affect the watermark copy
OpenCV's exactly (see tests/test_imgops.py, which compares against cv2 when it
is installed).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

# OpenCV COLOR_BGR2YUV / YUV2BGR for float images (delta = 0.5, as cv2 uses for float input)
_KY = (0.114, 0.587, 0.299)          # B, G, R weights
_KU, _KV = 0.492, 0.877
_IB, _IGU, _IGV, _IR = 2.032, -0.395, -0.581, 1.140


def bgr_to_yuv(bgr: np.ndarray) -> np.ndarray:
    b, g, r = (bgr[..., i].astype(np.float32) for i in range(3))
    y = np.float32(_KY[0]) * b + np.float32(_KY[1]) * g + np.float32(_KY[2]) * r
    u = (b - y) * np.float32(_KU) + np.float32(0.5)
    v = (r - y) * np.float32(_KV) + np.float32(0.5)
    return np.stack([y, u, v], axis=-1)


def yuv_to_bgr(yuv: np.ndarray) -> np.ndarray:
    y, u, v = (yuv[..., i] for i in range(3))
    u = u - 0.5
    v = v - 0.5
    return np.stack([y + _IB * u, y + _IGU * u + _IGV * v, y + _IR * v], axis=-1)


def gray(bgr: np.ndarray) -> np.ndarray:
    return (bgr[..., 0] * 0.114 + bgr[..., 1] * 0.587 + bgr[..., 2] * 0.299).astype(np.float32)


def resize(bgr: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Bicubic resize of a uint8 3-channel image to (w, h)."""
    if (bgr.shape[1], bgr.shape[0]) == tuple(size):
        return bgr
    img = Image.fromarray(np.ascontiguousarray(bgr[..., ::-1]).astype(np.uint8), "RGB")
    return np.asarray(img.resize(tuple(size), Image.Resampling.BICUBIC))[..., ::-1].copy()


def _integral(a: np.ndarray) -> np.ndarray:
    s = np.zeros((a.shape[0] + 1, a.shape[1] + 1), np.float64)
    s[1:, 1:] = a.cumsum(0).cumsum(1)
    return s


def box_sum(a: np.ndarray, kh: int, kw: int) -> np.ndarray:
    """Sum over a kh x kw window centred on each pixel (edges clipped)."""
    h, w = a.shape
    s = _integral(a)
    ry, rx = kh // 2, kw // 2
    y0 = np.clip(np.arange(h) - ry, 0, h)
    y1 = np.clip(np.arange(h) + kh - ry, 0, h)
    x0 = np.clip(np.arange(w) - rx, 0, w)
    x1 = np.clip(np.arange(w) + kw - rx, 0, w)
    return s[y1][:, x1] - s[y0][:, x1] - s[y1][:, x0] + s[y0][:, x0]


def box_mean(a: np.ndarray, k: int) -> np.ndarray:
    ones = np.ones_like(a, dtype=np.float64)
    return box_sum(a.astype(np.float64), k, k) / box_sum(ones, k, k)


def dilate(mask: np.ndarray, kh: int, kw: int) -> np.ndarray:
    return box_sum(mask.astype(np.float64), kh, kw) > 0


def erode(mask: np.ndarray, kh: int, kw: int) -> np.ndarray:
    ones = np.ones(mask.shape, np.float64)
    return box_sum(mask.astype(np.float64), kh, kw) >= box_sum(ones, kh, kw) - 0.5


def label_boxes(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """8-connected components of a boolean mask -> [(x, y, w, h, pixel_count)].

    Run-length union-find: fast enough for page-sized masks because it works on
    horizontal runs, not pixels.
    """
    h, w = mask.shape
    padded = np.zeros((h, w + 2), np.int8)
    padded[:, 1:-1] = mask
    d = np.diff(padded, axis=1)
    starts_r, starts_c = np.nonzero(d == 1)
    ends_r, ends_c = np.nonzero(d == -1)        # exclusive end column
    n = len(starts_r)
    if n == 0:
        return []
    parent = np.arange(n)

    def find(i):
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    row_first = np.searchsorted(starts_r, np.arange(h + 1))
    for r in range(1, h):
        a0, a1 = row_first[r - 1], row_first[r]
        b0, b1 = row_first[r], row_first[r + 1]
        i, j = a0, b0
        while i < a1 and j < b1:
            # 8-connectivity: runs touch if they overlap with one column of slack
            if starts_c[i] <= ends_c[j] and starts_c[j] <= ends_c[i]:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
            if ends_c[i] < ends_c[j]:
                i += 1
            else:
                j += 1
    roots = np.array([find(i) for i in range(n)])
    out = {}
    for k in range(n):
        r = roots[k]
        x0, x1, y = starts_c[k], ends_c[k], starts_r[k]
        if r in out:
            b = out[r]
            b[0] = min(b[0], x0); b[1] = min(b[1], y); b[2] = max(b[2], x1); b[3] = max(b[3], y + 1); b[4] += x1 - x0
        else:
            out[r] = [x0, y, x1, y + 1, x1 - x0]
    return [(int(b[0]), int(b[1]), int(b[2] - b[0]), int(b[3] - b[1]), int(b[4])) for b in out.values()]
