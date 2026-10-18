import numpy as np
import pytest
from PIL import Image

from sigwm import core
from sigwm.vendor import bwm

from .conftest import FIXTURE, PASSWORD


@pytest.mark.parametrize("mode", core.MODES)
def test_embed_roundtrip_and_robustness(mode):
    img, _ = core.load_signature(FIXTURE)
    sid = core.new_short_id()
    r = core.embed_signature(img, PASSWORD, core.CarrierParams(mode=mode), "SIG-20261017-" + sid, sid)
    assert core.extract(r.image, PASSWORD).text == sid
    for label, ok, got in core.robustness_test(r.image, PASSWORD, sid):
        assert ok, f"{mode} / {label}: {got!r}"


def test_alpha_is_preserved():
    img, _ = core.load_signature(FIXTURE)
    p = core.CarrierParams(mode="feathered")
    r = core.embed_signature(img, PASSWORD, p, "SIG-x-W0000001", "W0000001")
    master, _ = core.prepare_master(img, p.padding)
    expected = core.build_carrier(master, p, 0).getchannel("A")
    assert np.array_equal(np.asarray(expected), np.asarray(r.image.getchannel("A")))


def test_short_id_is_always_63_bits():
    for _ in range(200):
        assert core.short_id_bits(core.new_short_id()).size == core.WM_SHAPE


def test_wrong_password_does_not_extract():
    img, _ = core.load_signature(FIXTURE)
    r = core.embed_signature(img, PASSWORD, core.CarrierParams(), "SIG-x-W1234ABC", "W1234ABC")
    assert core.extract(r.image, "another-password-123").text != "W1234ABC"


def test_short_password_rejected():
    with pytest.raises(core.WatermarkError):
        core.password_seeds("short")


def test_blank_image_rejected():
    with pytest.raises(core.WatermarkError):
        core.prepare_master(Image.new("RGBA", (400, 200)), 64)


def test_vendored_matches_upstream(tmp_path):
    """Same pixels as guofei9987/blind_watermark, and same decoded values."""
    upstream = pytest.importorskip("blind_watermark")
    upstream.bw_notes.close()
    cv2 = pytest.importorskip("cv2")
    rng = np.random.default_rng(1)
    img = rng.integers(40, 220, size=(200, 330, 3), dtype=np.uint8)
    src = tmp_path / "src.png"
    cv2.imwrite(str(src), img)
    si, sw = core.password_seeds(PASSWORD)
    wm = upstream.WaterMark(password_img=si, password_wm=sw)
    wm.read_img(filename=str(src))
    wm.read_wm("W5A5A5A5", mode="str")
    ref = wm.embed()
    ours, _ = bwm.embed(img, "W5A5A5A5", si, sw)
    # float math differs slightly from OpenCV's; after rounding to 8 bits almost every pixel is identical
    diff = np.abs(np.round(np.clip(ref, 0, 255)) - np.round(np.clip(ours, 0, 255)))
    assert diff.max() <= 1 and (diff > 0).mean() < 0.01
    out = np.clip(np.round(ref), 0, 255).astype(np.uint8)
    cv2.imwrite(str(tmp_path / "o.png"), out)
    up_text = upstream.WaterMark(password_img=si, password_wm=sw).extract(filename=str(tmp_path / "o.png"), wm_shape=63, mode="str")
    assert up_text == bwm.extract_str(out, 63, si, sw) == "W5A5A5A5"


def test_old_script_format_still_extracts():
    """The old script embedded into raw RGB; extract_candidates tries that too."""
    img, _ = core.load_signature(FIXTURE)
    p = core.CarrierParams(mode="feathered_texture")
    master, _ = core.prepare_master(img, p.padding)
    carrier = core.build_carrier(master, p, 5)
    si, sw = core.password_seeds(PASSWORD)
    rgba = np.asarray(carrier)
    arr = np.ascontiguousarray(rgba[:, :, [2, 1, 0, 3]])
    out, _ = bwm.embed(arr, "W00C0FFE", si, sw)
    old = Image.fromarray(np.ascontiguousarray(out[:, :, [2, 1, 0, 3]]), "RGBA")
    texts = [r.text for r in core.extract_candidates(old, PASSWORD)]
    assert "W00C0FFE" in texts
