import numpy as np
import pytest
from PIL import Image, ImageDraw

from sigwm import background, core, service
from .conftest import PASSWORD


def paper_signature(paper=(244, 237, 222), ink=(22, 50, 135)):
    image = Image.new("RGB", (600, 280), paper)
    draw = ImageDraw.Draw(image)
    points = [(80, 150), (125, 70), (180, 170), (240, 95), (300, 155), (355, 65), (425, 150), (500, 100)]
    draw.line(points, fill=ink, width=7)
    return image.convert("RGBA")


@pytest.mark.parametrize("paper,ink", [((255, 255, 255), (20, 20, 20)),
                                      ((244, 237, 222), (22, 50, 135)),
                                      ((218, 222, 224), (155, 30, 35))])
def test_removes_paper_and_retains_colored_strokes(paper, ink):
    source = paper_signature(paper, ink)
    result = background.remove_paper(source)
    a = np.asarray(result.getchannel("A"))
    assert a[:40].max() == 0
    assert a[150, 80] == 255
    assert np.array_equal(np.asarray(source)[150, 80, :3], ink)
    assert result.getchannel("A").getbbox()[0] > 0


def test_existing_transparent_signature_is_not_modified():
    image = paper_signature()
    image.putalpha(110)
    assert np.array_equal(np.asarray(background.remove_paper(image)), np.asarray(image))


def test_gradual_paper_shadow_is_removed():
    image = paper_signature((255, 255, 255), (30, 30, 30))
    rgb = np.asarray(image).copy()
    gradient = np.linspace(0.66, 1, image.width)[None, :, None]
    rgb[:, :, :3] = np.round(rgb[:, :, :3] * gradient).astype(np.uint8)
    a = np.asarray(background.remove_paper(Image.fromarray(rgb)).getchannel("A"))
    assert (a[:40] == 0).mean() > 0.99
    assert a[150, 80] > 240


def test_threshold_can_restore_faint_strokes_and_empty_paper_is_rejected():
    image = paper_signature((255, 255, 255), (232, 232, 232))
    assert background.remove_paper(image, 220).getchannel("A").getbbox() is None
    assert background.remove_paper(image, 245).getchannel("A").getbbox() is not None
    with pytest.raises(core.WatermarkError):
        core.prepare_signature(Image.new("RGBA", (600, 280), "white"), core.CarrierParams())


@pytest.mark.parametrize("mode", core.MODES)
def test_opaque_input_gets_selected_carrier_and_readable_watermark(mode, tmp_path, store):
    source = paper_signature()
    path = tmp_path / "paper.png"
    source.save(path)
    p = core.CarrierParams(mode=mode)
    result = service.embed_file(store, path, PASSWORD, p, "paper signature")
    assert result.ok, result.error
    out = Image.open(result.out_path)
    expected = core.render_preview(source, p)
    assert np.array_equal(np.asarray(out.getchannel("A")), np.asarray(expected.getchannel("A")))
    assert core.extract(out, PASSWORD).text == result.record.short_id
    assert result.record.params["remove_background"] is True
    if mode == "white":
        assert out.getchannel("A").getextrema() == (255, 255)
    elif mode == "translucent":
        assert np.asarray(out.getchannel("A"))[0, 0] == p.alpha
    else:
        assert np.asarray(out.getchannel("A"))[0, 0] == 0
        assert np.asarray(out.getchannel("A"))[p.feather + 2, p.feather + 2] == p.alpha
    assert out.width < source.width + p.padding * 2


def test_background_removal_can_be_disabled_and_padding_is_added():
    source = paper_signature()
    p = core.CarrierParams(remove_background=False)
    assert np.array_equal(np.asarray(core.prepare_signature(source, p)), np.asarray(source))
    tight = Image.new("RGBA", (350, 100), (10, 30, 90, 255))
    master, bbox = core.prepare_master(tight, 64)
    assert master.size == (478, 228)
    assert bbox == (64, 64, 414, 164)


def test_preview_refreshes_the_same_preparation_when_options_change(tmp_path):
    from sigwm.gui.page_embed import load_item, prepare_item

    path = tmp_path / "signature.jpg"
    paper_signature().convert("RGB").save(path, quality=90)
    p = core.CarrierParams()
    item = load_item(path, p)
    assert not item.error and item.background_removed
    source, _ = core.load_signature(path)
    assert np.array_equal(np.asarray(item.small), np.asarray(core.prepare_signature(source, p)))
    p.remove_background = False
    prepare_item(item, p)
    assert not item.background_removed
    assert item.small.getchannel("A").getextrema() == (255, 255)
    p.remove_background = True
    prepare_item(item, p)
    assert item.background_removed and item.small.getchannel("A").getextrema()[0] == 0


def test_camera_orientation_is_applied_before_preparation(tmp_path):
    image = paper_signature().convert("RGB")
    exif = image.getexif()
    exif[274] = 6
    path = tmp_path / "rotated.jpg"
    image.save(path, exif=exif)
    loaded, _ = core.load_signature(path)
    assert loaded.size == (280, 600)


def test_transparent_corners_do_not_preserve_an_opaque_paper_rectangle():
    source = paper_signature()
    pixels = np.asarray(source).copy()
    pixels[:12, :12, 3] = 0
    image = Image.fromarray(pixels)
    assert background.has_paper_background(image)
    result = core.prepare_signature(image, core.CarrierParams())
    assert np.asarray(result.getchannel("A"))[:40].max() == 0
    assert np.asarray(result.getchannel("A"))[150, 80] == 255


# ---------------------------------------------------------------- 1.0.4: hard backgrounds

from .hard_backgrounds import CASES, score  # noqa: E402


@pytest.mark.parametrize("name", sorted(CASES))
def test_hard_backgrounds_keep_ink_and_drop_the_rest(name):
    """Ruled/grid paper, form lines (also crossed by a black pen), a desk at the edge,
    uneven light and recycled paper: the signature stays, the rest goes."""
    img, gt = CASES[name]()
    alpha = np.asarray(background.remove_paper(img.convert("RGBA")).getchannel("A"))
    ink_kept, junk_kept = score(alpha, gt)
    assert ink_kept >= 0.97, ink_kept
    assert junk_kept <= 0.02, junk_kept


def test_signer_underline_is_not_taken_for_a_ruled_line():
    img, gt = CASES["ruled"]()
    alpha = np.asarray(background.remove_paper(img.convert("RGBA")).getchannel("A"))
    # the drawn underline runs from x=150 to 560 around y=285-300
    assert (alpha[280:305, 200:500] > 128).sum() > 0.8 * gt[280:305, 200:500].sum()


def test_tilted_rules_are_found():
    img, gt = CASES["ruled"]()
    tilted = img.rotate(6, Image.Resampling.BICUBIC, fillcolor=(250, 250, 246))
    gt_t = np.asarray(Image.fromarray(gt.astype(np.uint8) * 255).rotate(6, Image.Resampling.NEAREST)) > 127
    alpha = np.asarray(background.remove_paper(tilted.convert("RGBA")).getchannel("A"))
    ink_kept, junk_kept = score(alpha, gt_t)
    assert ink_kept >= 0.95 and junk_kept <= 0.03, (ink_kept, junk_kept)
