import dataclasses

import pytest
from PIL import Image, ImageDraw

from sigwm import core, trace

from .conftest import PASSWORD


def _page(sig: Image.Image, scale: float, path, quality=90):
    page = Image.new("RGB", (1700, 2200), "white")
    d = ImageDraw.Draw(page)
    for y in range(150, 1500, 45):
        d.rectangle([150, y, 1550 - (y % 7) * 40, y + 14], fill=(60, 60, 60))
    s = sig.resize((int(sig.width * scale), int(sig.height * scale)), Image.Resampling.LANCZOS)
    page.paste(s, (313, 1641), s)
    page.save(path, quality=quality)
    return path


def test_pdf_with_embedded_signature(signed, tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    store, outs = signed
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 72), "Contract")
    p.insert_image(pymupdf.Rect(72, 600, 272, 662), filename=str(outs[1].out_path))
    doc.save(tmp_path / "c.pdf")
    res = trace.analyze(store, PASSWORD, tmp_path / "c.pdf")
    assert [(h.kind, h.record.id) for h in res.hits] == [("match", outs[1].record.id)]


def test_docx_with_embedded_signature(signed, tmp_path):
    docx = pytest.importorskip("docx")
    store, outs = signed
    d = docx.Document()
    d.add_paragraph("hello")
    d.add_picture(str(outs[2].out_path))
    d.save(tmp_path / "c.docx")
    res = trace.analyze(store, PASSWORD, tmp_path / "c.docx")
    assert [(h.kind, h.record.id) for h in res.hits] == [("match", outs[2].record.id)]


def test_signature_located_on_page_photo(signed, tmp_path):
    store, outs = signed
    sig = Image.open(outs[2].out_path)
    res = trace.analyze(store, PASSWORD, _page(sig, 1.3, tmp_path / "p.jpg"))
    assert any(h.kind == "match" and h.record.id == outs[2].record.id for h in res.hits)


def test_no_false_match_for_someone_elses_mark(signed, tmp_path):
    """A clean watermark whose ID is not in the records must not be reported as a match."""
    store, outs = signed
    sig = Image.open(outs[2].out_path)
    page = _page(sig, 1.0, tmp_path / "p.jpg")
    fakes = [dataclasses.replace(r, id=f"X{i}", short_id=core.new_short_id()) for i in range(10) for r in store.records()]
    with store._lock:
        store.db.execute("DELETE FROM records")
        store.db.commit()
    for f in fakes:
        store.add_record(f)
    res = trace.analyze(store, PASSWORD, page)
    assert all(h.kind == "none" for h in res.hits)
    direct = trace.analyze(store, PASSWORD, outs[0].out_path)
    assert all(h.kind == "none" for h in direct.hits)


def test_resized_signature_image(signed, tmp_path):
    store, outs = signed
    sig = Image.open(outs[0].out_path)
    small = sig.resize((sig.width * 3 // 4, sig.height * 3 // 4), Image.Resampling.LANCZOS)
    small.save(tmp_path / "s.png")
    res = trace.analyze(store, PASSWORD, tmp_path / "s.png")
    assert res.hits and res.hits[0].kind == "match" and res.hits[0].record.id == outs[0].record.id
