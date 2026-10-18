from pathlib import Path

import pytest

from sigwm import backup, core, secret, service
from sigwm.storage import Store

from .conftest import FIXTURE, PASSWORD


def test_embed_creates_record_and_files(signed):
    store, outs = signed
    assert store.record_count() == 3
    u = store.usage()
    assert u["uploads"]["count"] == 3 and u["outputs"]["count"] == 3
    rec = store.record_by_short(outs[0].record.short_id)
    assert rec and Path(rec.out_path).exists() and rec.sig_bbox[2] > rec.sig_bbox[0]


def test_failed_embed_reports_error(store, tmp_path):
    from PIL import Image
    blank = tmp_path / "blank.png"
    Image.new("RGBA", (300, 200)).save(blank)
    o = service.embed_file(store, blank, PASSWORD, core.CarrierParams(), "x")
    assert not o.ok and "可見像素" in o.error


def test_password_fallback_without_keyring(store):
    assert secret.set_password(store, PASSWORD) == "file"
    assert secret.get_password(store) == PASSWORD


def test_backup_restore_roundtrip(signed, tmp_path):
    store, _ = signed
    secret.set_password(store, PASSWORD)
    path = backup.create(store, tmp_path / "bk", ["settings", "records", "uploads", "outputs"], "backup-pass", True)
    assert backup.is_encrypted(path)
    with pytest.raises(backup.BackupError):
        backup.read_manifest(path, "wrong-pass")
    assert store.usage()["uploads"]["backed_count"] == 3

    other = Store(tmp_path / "other", True)
    s = backup.restore(other, path, ["settings", "records", "outputs"], "backup-pass")
    assert s["records_added"] == 3 and s["files"] == 3 and s["password"]
    assert secret.get_password(other) == PASSWORD
    for r in other.records():
        assert Path(r.out_path).exists()
    again = backup.restore(other, path, ["records"], "backup-pass")
    assert again["records_skipped"] == 3
    other.close()


def test_unencrypted_backup(signed, tmp_path):
    store, _ = signed
    path = backup.create(store, tmp_path, ["records"])
    assert not backup.is_encrypted(path)
    assert backup.read_manifest(path)["parts"] == ["records"]


def test_cleanup_only_backed_up(signed, tmp_path):
    store, _ = signed
    n, _ = store.delete_files(["uploads"], only_backed_up=True)
    assert n == 0                                     # nothing backed up yet
    backup.create(store, tmp_path, ["uploads"])
    service.embed_file(store, FIXTURE, PASSWORD, core.CarrierParams(), "later")   # one new, unbacked upload
    n, freed = store.delete_files(["uploads"], only_backed_up=True)
    assert n == 3 and freed > 0
    assert store.usage()["uploads"]["count"] == 1
    assert store.record_count() == 4                  # records are never cleaned


def test_import_legacy(store, tmp_path):
    d = tmp_path / "out" / "watermark"
    d.mkdir(parents=True)
    (d / "SIG-20260922-W12AB34C.txt").write_text(
        "FORMAT=SIG-BLIND-WM-1\nID=SIG-20260922-W12AB34C\nSHORT_ID=W12AB34C\nWM_SHAPE=63\nWIDTH=900\nHEIGHT=400\n"
        "BACKGROUND=feathered_texture\nPURPOSE=old\n", encoding="utf-8")
    assert service.import_legacy(store, tmp_path / "out") == (1, 0)
    assert service.import_legacy(store, tmp_path / "out") == (0, 1)
    assert store.record_by_short("W12AB34C").format == "SIG-BLIND-WM-1"
