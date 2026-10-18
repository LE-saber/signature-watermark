"""Selective backup (.swbak) and restore.

A .swbak is a zip file; with a backup password it is AES-256 encrypted (WinZip AES,
via pyzipper). Inside:

    manifest.json   format, parts, file map
    settings.json   settings without the password
    secret.json     watermark password (only if the user ticked it, encrypted backups only)
    records.json    all signing records
    files/<kind>/…  images and documents
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import pyzipper

from . import secret
from .storage import KINDS, Record, Store, now_iso
from .i18n import tr

FORMAT = "SWBAK-1"
PARTS = ("settings", "records", "uploads", "outputs", "docs")
PART_LABELS = {"settings": tr('設定'), "records": tr('簽發記錄'), "uploads": tr('原始圖片'), "outputs": tr('水印圖片'), "docs": tr('溯源文件')}

Progress = Callable[[int, int, str], None]


class BackupError(Exception):
    pass


def _files_for(store: Store, part: str) -> list[tuple[Path, dict]]:
    """(path, info) pairs for a file part. Outputs also include record outputs saved
    outside the data folder, as long as they still exist."""
    out: dict[str, tuple[Path, dict]] = {}
    for row in store.files(part):
        p = Path(row["path"])
        if p.exists():
            out[str(p.resolve())] = (p, {})
    if part == "outputs":
        for r in store.records():
            p = Path(r.out_path)
            if r.out_path and p.exists():
                out.setdefault(str(p.resolve()), (p, {}))[1]["record"] = r.id
    return list(out.values())


def estimate(store: Store, parts: list[str]) -> int:
    total = 0
    for part in parts:
        if part in ("uploads", "outputs", "docs"):
            total += sum(p.stat().st_size for p, _ in _files_for(store, part))
        elif part == "records":
            total += store.record_count() * 600
        else:
            total += 2048
    return total


def create(store: Store, dest_dir: Path, parts: list[str], password: str = "",
           include_wm_password: bool = False, progress: Progress | None = None) -> Path:
    parts = [p for p in PARTS if p in parts]
    if not parts:
        raise BackupError(tr('請至少選一項'))
    if include_wm_password and not password:
        raise BackupError(tr('備份水印密碼時必須加密備份文件'))
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = dest_dir / f"SigWatermark-backup-{stamp}.swbak"

    jobs: list[tuple[str, Path, dict]] = []
    for part in ("uploads", "outputs", "docs"):
        if part in parts:
            for i, (p, info) in enumerate(_files_for(store, part)):
                jobs.append((f"files/{part}/{i:05d}-{p.name}", p, {"part": part, **info}))

    tmp = path.with_suffix(".partial")
    try:
        if password:
            zf = pyzipper.AESZipFile(tmp, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES)
            zf.setpassword(password.encode("utf-8"))
        else:
            zf = zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED)
        with zf:
            manifest = {"format": FORMAT, "created": now_iso(), "parts": parts, "data_dir": str(store.root),
                        "files": {arc: info for arc, _, info in jobs}, "has_secret": include_wm_password}
            if "settings" in parts:
                zf.writestr("settings.json", json.dumps(store.settings.public_dict(), ensure_ascii=False, indent=2))
            if "records" in parts:
                zf.writestr("records.json", json.dumps([asdict(r) for r in store.records()], ensure_ascii=False, indent=1))
            if include_wm_password:
                zf.writestr("secret.json", json.dumps({"watermark_password": secret.get_password(store)}))
            for i, (arc, p, _) in enumerate(jobs):
                if progress:
                    progress(i, len(jobs), p.name)
                zf.write(p, arc)
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if progress:
        progress(len(jobs), len(jobs), "")
    store.mark_backed_up([p for p in parts if p in KINDS], now_iso())
    store.add_backup(path, path.stat().st_size, parts, bool(password))
    return path


def _open(path: Path, password: str):
    zf = pyzipper.AESZipFile(path, "r")
    if password:
        zf.setpassword(password.encode("utf-8"))
    return zf


def is_encrypted(path: Path) -> bool:
    with pyzipper.AESZipFile(path, "r") as zf:
        info = zf.getinfo("manifest.json")
        return bool(info.flag_bits & 0x1)


def read_manifest(path: Path, password: str = "") -> dict:
    try:
        with _open(path, password) as zf:
            m = json.loads(zf.read("manifest.json"))
    except RuntimeError as exc:  # pyzipper: bad or missing password
        raise BackupError(tr('備份密碼不正確') if password else tr('這份備份已加密，請輸入備份密碼')) from exc
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise BackupError(tr('這不是有效的 SigWatermark 備份文件')) from exc
    if m.get("format") != FORMAT:
        raise BackupError(tr('不支持的備份格式：{v}', v=m.get('format')))
    return m


def restore(store: Store, path: Path, parts: list[str], password: str = "", overwrite: bool = False,
            progress: Progress | None = None) -> dict:
    m = read_manifest(path, password)
    parts = [p for p in parts if p in m["parts"]]
    summary = {"records_added": 0, "records_skipped": 0, "files": 0, "password": False}
    with _open(path, password) as zf:
        if "settings" in parts and "settings.json" in zf.namelist():
            data = json.loads(zf.read("settings.json"))
            for k, v in data.items():
                if hasattr(store.settings, k) and k not in ("password_fallback", "output_dir", "backup_dir"):
                    setattr(store.settings, k, v)
            store.save_settings()
        if m.get("has_secret") and "secret.json" in zf.namelist() and ("settings" in parts or overwrite):
            pw = json.loads(zf.read("secret.json")).get("watermark_password", "")
            if pw:
                secret.set_password(store, pw)
                summary["password"] = True

        restored_out: dict[str, Path] = {}
        file_parts = [p for p in ("uploads", "outputs", "docs") if p in parts]
        if overwrite and file_parts:
            store.delete_files(file_parts, only_backed_up=False)
        items = [(arc, info) for arc, info in m["files"].items() if info["part"] in file_parts]
        for i, (arc, info) in enumerate(items):
            name = arc.split("/", 2)[2].split("-", 1)[1]
            target_dir = store.kind_dir(info["part"])
            target = target_dir / name
            n = 2
            while target.exists():
                target = target_dir / f"{Path(name).stem}-{n}{Path(name).suffix}"
                n += 1
            target.write_bytes(zf.read(arc))
            store.track(target, info["part"])
            if info.get("record"):
                restored_out[info["record"]] = target
            summary["files"] += 1
            if progress:
                progress(i + 1, len(items), name)

        if "records" in parts and "records.json" in zf.namelist():
            recs = json.loads(zf.read("records.json"))
            if overwrite:
                with store._lock:
                    store.db.execute("DELETE FROM records")
                    store.db.commit()
            existing = {r.id for r in store.records()}
            for d in recs:
                d["sig_bbox"] = tuple(d.get("sig_bbox") or (0, 0, 0, 0))
                rec = Record(**d)
                if rec.id in existing:
                    summary["records_skipped"] += 1
                    continue
                if rec.id in restored_out and not Path(rec.out_path).exists():
                    rec.out_path = str(restored_out[rec.id])
                store.add_record(rec)
                summary["records_added"] += 1
    # restored files came from a backup, so they are backed up by definition
    if file_parts:
        with store._lock:
            store.db.execute("UPDATE files SET backed_up=? WHERE backed_up IS NULL AND kind IN (%s)" %
                             ",".join("?" * len(file_parts)), (now_iso(), *file_parts))
            store.db.commit()
    return summary
