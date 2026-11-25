from dataclasses import replace
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
        assert Path(r.out_path).parent == other.kind_dir("outputs")
        assert core.sha256_file(Path(r.out_path)) == r.out_sha256
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



def test_merge_restored_files_do_not_flag_unarchived_files(signed, tmp_path):
    source, _ = signed
    archive = backup.create(source, tmp_path / "bk", ["outputs"])
    dest = Store(tmp_path / "dest", True)
    try:
        new_png = dest.kind_dir("outputs") / Path(source.files("outputs")[0]["path"]).name
        new_png.write_bytes(b"unarchived local output")
        dest.track(new_png, "outputs")
        result = backup.restore(dest, archive, ["outputs"])
        assert result["files"] == 3
        flags = {Path(row["path"]): row["backed_up"] for row in dest.files("outputs")}
        assert not flags[new_png]
        assert all(flag for path, flag in flags.items() if path != new_png)
        assert dest.delete_files(["outputs"], only_backed_up=True)[0] == 3
        assert new_png.read_bytes() == b"unarchived local output"
    finally:
        dest.close()


def test_create_does_not_flag_files_tracked_after_snapshot(store, tmp_path):
    folder = store.kind_dir("outputs")
    included, late = folder / "included.png", folder / "late.png"
    included.write_bytes(b"archived")
    store.track(included, "outputs")

    def add_late_file(done, total, name):
        if done == 0:
            late.write_bytes(b"not archived")
            store.track(late, "outputs")

    path = backup.create(store, tmp_path / "bk", ["outputs"], progress=add_late_file)
    assert len(backup.read_manifest(path)["files"]) == 1
    flags = {Path(row["path"]): row["backed_up"] for row in store.files("outputs")}
    assert flags[included] and not flags[late]


@pytest.mark.parametrize("matching_hash", [True, False])
def test_merge_relinks_missing_duplicate_output_only_on_hash_match(signed, tmp_path, matching_hash):
    source, outs = signed
    archive = backup.create(source, tmp_path / "bk", ["records", "outputs"])
    original = outs[0].record
    dest = Store(tmp_path / "dest", True)
    old_path = str(tmp_path / "missing" / "old.png")
    try:
        dest.add_record(replace(original, purpose="keep local edits", out_path=old_path,
                                out_sha256=original.out_sha256 if matching_hash else "0" * 64))
        result = backup.restore(dest, archive, ["records", "outputs"])
        assert result["records_skipped"] == 1 and result["records_added"] == 2
        record = dest.record_by_short(original.short_id)
        assert record.purpose == "keep local edits"
        if matching_hash:
            output = Path(record.out_path)
            assert output.parent == dest.kind_dir("outputs")
            assert core.sha256_file(output) == original.out_sha256
        else:
            assert record.out_path == old_path
    finally:
        dest.close()


def test_upgrade_clears_unverified_legacy_flags_only_once(tmp_path):
    dest = Store(tmp_path / "existing", True)
    output = dest.kind_dir("outputs") / "local.png"
    output.write_bytes(b"only copy")
    dest.track(output, "outputs")
    with dest.db:
        dest.db.execute("UPDATE files SET backed_up = 'old-flag'")
        dest.db.execute("PRAGMA user_version = 0")
    dest.close()
    dest = Store(tmp_path / "existing", True)
    try:
        assert not dest.files("outputs")[0]["backed_up"]
        assert dest.delete_files(["outputs"], only_backed_up=True)[0] == 0
        assert output.exists()
        backup.create(dest, tmp_path / "bk", ["outputs"])
    finally:
        dest.close()
    dest = Store(tmp_path / "existing", True)
    try:
        assert dest.files("outputs")[0]["backed_up"]
    finally:
        dest.close()


def test_import_legacy(store, tmp_path):
    d = tmp_path / "out" / "watermark"
    d.mkdir(parents=True)
    (d / "SIG-20260922-W12AB34C.txt").write_text(
        "FORMAT=SIG-BLIND-WM-1\nID=SIG-20260922-W12AB34C\nSHORT_ID=W12AB34C\nWM_SHAPE=63\nWIDTH=900\nHEIGHT=400\n"
        "BACKGROUND=feathered_texture\nPURPOSE=old\n", encoding="utf-8")
    assert service.import_legacy(store, tmp_path / "out") == (1, 0)
    assert service.import_legacy(store, tmp_path / "out") == (0, 1)
    assert store.record_by_short("W12AB34C").format == "SIG-BLIND-WM-1"


def test_generated_password_is_strong_and_readable():
    seen = set()
    for _ in range(50):
        pw = secret.generate_password()
        assert len(pw) == 29 and pw.count("-") == 5
        assert not set(pw) & set("0O1lI")
        core.password_seeds(pw)          # accepted as a watermark password
        seen.add(pw)
    assert len(seen) == 50


def test_old_default_opacity_is_migrated(tmp_path):
    import json
    from sigwm.storage import Settings
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"alpha": 96, "mode": "feathered"}), encoding="utf-8")
    assert Settings.load(path).alpha == 24
    path.write_text(json.dumps({"alpha": 140}), encoding="utf-8")
    assert Settings.load(path).alpha == 140          # a value the user picked is kept
    path.write_text(json.dumps({"alpha": 96, "settings_version": 2}), encoding="utf-8")
    assert Settings.load(path).alpha == 96
