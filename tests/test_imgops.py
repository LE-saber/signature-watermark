import numpy as np
import pytest

from sigwm import imgops

cv2 = pytest.importorskip("cv2")


def test_yuv_matches_opencv():
    x = np.random.default_rng(0).uniform(0, 255, (64, 80, 3)).astype(np.float32)
    ours = imgops.bgr_to_yuv(x)
    assert np.abs(ours - cv2.cvtColor(x, cv2.COLOR_BGR2YUV)).max() < 1e-3
    assert np.abs(imgops.yuv_to_bgr(ours) - cv2.cvtColor(ours, cv2.COLOR_YUV2BGR)).max() < 1e-2


def test_labels_match_opencv():
    rng = np.random.default_rng(3)
    mask = rng.random((120, 160)) > 0.93
    mask = imgops.dilate(mask, 3, 5)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    ref = sorted(tuple(int(v) for v in stats[i]) for i in range(1, n))
    assert sorted(imgops.label_boxes(mask)) == ref


def test_dilate_matches_opencv():
    mask = np.random.default_rng(5).random((50, 70)) > 0.97
    ref = cv2.dilate(mask.astype(np.uint8), np.ones((3, 7), np.uint8)) > 0
    assert np.array_equal(imgops.dilate(mask, 3, 7), ref)
