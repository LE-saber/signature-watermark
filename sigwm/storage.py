"""Data directory, settings, signing records and tracked files.

Layout (portable mode puts it next to the program):

    data/
      settings.json
      records.sqlite      signing records + tracked files
      uploads/            copies of source signatures that were watermarked
      out/                default output folder for watermarked images
      docs/               documents imported for tracing
      cache/              temporary files, safe to delete any time
      backup/             default backup destination
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from .i18n import tr

APP_NAME = "SigWatermark"
KINDS = ("uploads", "outputs", "docs", "cache")
KIND_DIRS = {"uploads": "uploads", "outputs": "out", "docs": "docs", "cache": "cache"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def program_dir() -> Path:
    """Folder that holds the executable (frozen) or the project root (source)."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        # macOS: .../SigWatermark.app/Contents/MacOS/SigWatermark -> folder holding the .app
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent.parent
        return exe.parent
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def _translocated(path: Path) -> bool:
    # macOS runs quarantined apps from a random read-only mount.
    return "/AppTranslocation/" in str(path)


def resolve_data_dir() -> tuple[Path, bool]:
    """Returns (data dir, portable). A pointer file decides; portable is the default."""
    portable_dir = program_dir() / "data"
    pointer = program_dir() / "sigwatermark-location.txt"
    if pointer.exists() and pointer.read_text(encoding="utf-8").strip() == "user":
        return user_data_dir(), False
    if user_data_dir().joinpath("settings.json").exists() and not portable_dir.exists():
        return user_data_dir(), False
    if not _translocated(portable_dir) and _writable(portable_dir):
        return portable_dir, True
    return user_data_dir(), False


def set_storage_mode(portable: bool) -> None:
    pointer = program_dir() / "sigwatermark-location.txt"
    try:
        pointer.write_text("portable" if portable else "user", encoding="utf-8")
    except OSError:
        pass


@dataclass
class Settings:
    mode: str = "feathered_texture"
    padding: int = 64
    alpha: int = 96
    feather: int = 48
    texture: int = 4
    purpose: str = "signature-use"
    output_dir: str = ""          # empty = data/out
    naming: str = "SIG-{date}-{short}"
    self_check: bool = True
    backup_reminder_days: int = 30
    backup_dir: str = ""          # empty = data/backup
    language: str = ""            # empty = follow the system language
    password_fallback: str = ""   # only used when no OS keyring is available

    @classmethod
    def load(cls, path: Path) -> "Settings":
        s = cls()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
            except (OSError, ValueError):
                pass
        return s

    def save(self, path: Path) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def public_dict(self) -> dict:
        d = asdict(self)
        d.pop("password_fallback", None)
        return d


@dataclass
class Record:
    id: str
    short_id: str
    purpose: str
    mode: str
    width: int
    height: int
    sig_bbox: tuple[int, int, int, int]
    params: dict
    src_name: str
    src_sha256: str
    out_path: str
    out_sha256: str
    created: str
    format: str = "SIG-BLIND-WM-2"
    wm_shape: int = 63
    extra: dict = field(default_factory=dict)


SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY, short_id TEXT NOT NULL, purpose TEXT, mode TEXT,
  width INTEGER, height INTEGER, sig_bbox TEXT, params TEXT, src_name TEXT,
  src_sha256 TEXT, out_path TEXT, out_sha256 TEXT, created TEXT, format TEXT,
  wm_shape INTEGER, extra TEXT
);
CREATE INDEX IF NOT EXISTS records_short ON records(short_id);
CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY, kind TEXT NOT NULL, size INTEGER NOT NULL,
  created TEXT NOT NULL, backed_up TEXT
);
CREATE TABLE IF NOT EXISTS backups (
  path TEXT PRIMARY KEY, created TEXT, size INTEGER, parts TEXT, encrypted INTEGER
);
"""


class Store:
    def __init__(self, root: Path | None = None, portable: bool | None = None):
        if root is None:
            root, portable = resolve_data_dir()
        self.root = Path(root)
        self.portable = bool(portable)
        self.root.mkdir(parents=True, exist_ok=True)
        for d in (*KIND_DIRS.values(), "backup"):
            (self.root / d).mkdir(exist_ok=True)
        self.settings_path = self.root / "settings.json"
        self.settings = Settings.load(self.settings_path)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "records.sqlite", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ------------------------------------------------------------ paths
    def kind_dir(self, kind: str) -> Path:
        return self.root / KIND_DIRS[kind]

    @property
    def output_dir(self) -> Path:
        return Path(self.settings.output_dir) if self.settings.output_dir else self.kind_dir("outputs")

    @property
    def backup_dir(self) -> Path:
        return Path(self.settings.backup_dir) if self.settings.backup_dir else self.root / "backup"

    def save_settings(self) -> None:
        with self._lock:
            self.settings.save(self.settings_path)

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------ records
    def add_record(self, r: Record) -> None:
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.id, r.short_id, r.purpose, r.mode, r.width, r.height, json.dumps(list(r.sig_bbox)),
                 json.dumps(r.params), r.src_name, r.src_sha256, r.out_path, r.out_sha256, r.created,
                 r.format, r.wm_shape, json.dumps(r.extra, ensure_ascii=False)))
            self.db.commit()

    @staticmethod
    def _row(row: sqlite3.Row) -> Record:
        return Record(
            id=row["id"], short_id=row["short_id"], purpose=row["purpose"] or "", mode=row["mode"] or "",
            width=row["width"] or 0, height=row["height"] or 0,
            sig_bbox=tuple(json.loads(row["sig_bbox"] or "[0,0,0,0]")), params=json.loads(row["params"] or "{}"),
            src_name=row["src_name"] or "", src_sha256=row["src_sha256"] or "", out_path=row["out_path"] or "",
            out_sha256=row["out_sha256"] or "", created=row["created"] or "", format=row["format"] or "",
            wm_shape=row["wm_shape"] or 63, extra=json.loads(row["extra"] or "{}"))

    def records(self, query: str = "") -> list[Record]:
        with self._lock:
            if query:
                q = f"%{query}%"
                rows = self.db.execute(
                    "SELECT * FROM records WHERE id LIKE ? OR purpose LIKE ? OR src_name LIKE ? ORDER BY created DESC",
                    (q, q, q)).fetchall()
            else:
                rows = self.db.execute("SELECT * FROM records ORDER BY created DESC").fetchall()
        return [self._row(r) for r in rows]

    def record_by_short(self, short_id: str) -> Record | None:
        with self._lock:
            row = self.db.execute("SELECT * FROM records WHERE short_id=?", (short_id,)).fetchone()
        return self._row(row) if row else None

    def record_count(self) -> int:
        with self._lock:
            return self.db.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    def export_csv(self, path: Path) -> int:
        import csv
        recs = self.records()
        with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([tr('簽發ID'), tr('短ID'), tr('用途'), tr('載體'), tr('寬'), tr('高'), tr('源文件'), tr('源文件SHA256'), tr('輸出文件'), tr('輸出SHA256'), tr('建立時間')])
            for r in recs:
                w.writerow([r.id, r.short_id, r.purpose, r.mode, r.width, r.height, r.src_name, r.src_sha256,
                            r.out_path, r.out_sha256, r.created])
        return len(recs)

    # ------------------------------------------------------------ tracked files
    def track(self, path: Path, kind: str) -> None:
        path = Path(path)
        with self._lock:
            self.db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,NULL)",
                            (str(path.resolve()), kind, path.stat().st_size, now_iso()))
            self.db.commit()

    def files(self, kind: str) -> list[sqlite3.Row]:
        with self._lock:
            return self.db.execute("SELECT * FROM files WHERE kind=? ORDER BY created", (kind,)).fetchall()

    def prune_missing(self) -> None:
        with self._lock:
            rows = self.db.execute("SELECT path FROM files").fetchall()
            gone = [(r["path"],) for r in rows if not Path(r["path"]).exists()]
            if gone:
                self.db.executemany("DELETE FROM files WHERE path=?", gone)
                self.db.commit()

    def scan_cache(self) -> None:
        """The cache folder is not tracked file-by-file; register whatever is there."""
        cache = self.kind_dir("cache")
        known = {r["path"] for r in self.files("cache")}
        for p in cache.rglob("*"):
            if p.is_file() and str(p.resolve()) not in known:
                self.track(p, "cache")

    def usage(self) -> dict[str, dict]:
        self.prune_missing()
        self.scan_cache()
        out = {}
        for kind in KINDS:
            rows = self.files(kind)
            backed = [r for r in rows if r["backed_up"]]
            out[kind] = {
                "count": len(rows), "bytes": sum(r["size"] for r in rows),
                "backed_count": len(backed), "backed_bytes": sum(r["size"] for r in backed),
            }
        db_bytes = (self.root / "records.sqlite").stat().st_size if (self.root / "records.sqlite").exists() else 0
        out["records"] = {"count": self.record_count(), "bytes": db_bytes + (self.settings_path.stat().st_size if self.settings_path.exists() else 0)}
        return out

    def mark_backed_up(self, kinds: list[str], when: str) -> None:
        with self._lock:
            for k in kinds:
                self.db.execute("UPDATE files SET backed_up=? WHERE kind=?", (when, k))
            self.db.commit()

    def delete_files(self, kinds: list[str], only_backed_up: bool) -> tuple[int, int]:
        n = freed = 0
        with self._lock:
            for kind in kinds:
                rows = self.files(kind)
                for r in rows:
                    if only_backed_up and kind != "cache" and not r["backed_up"]:
                        continue
                    p = Path(r["path"])
                    try:
                        if p.exists():
                            p.unlink()
                        n += 1
                        freed += r["size"]
                    except OSError:
                        continue
                    self.db.execute("DELETE FROM files WHERE path=?", (r["path"],))
            if "cache" in kinds:
                shutil.rmtree(self.kind_dir("cache"), ignore_errors=True)
                self.kind_dir("cache").mkdir(exist_ok=True)
            self.db.commit()
        return n, freed

    # ------------------------------------------------------------ backups
    def add_backup(self, path: Path, size: int, parts: list[str], encrypted: bool) -> None:
        with self._lock:
            self.db.execute("INSERT OR REPLACE INTO backups VALUES (?,?,?,?,?)",
                            (str(path), now_iso(), size, json.dumps(parts), int(encrypted)))
            self.db.commit()

    def backups(self) -> list[dict]:
        with self._lock:
            rows = self.db.execute("SELECT * FROM backups ORDER BY created DESC").fetchall()
        return [{"path": r["path"], "created": r["created"], "size": r["size"],
                 "parts": json.loads(r["parts"]), "encrypted": bool(r["encrypted"]),
                 "exists": Path(r["path"]).exists()} for r in rows]

    def last_backup(self) -> str | None:
        with self._lock:
            row = self.db.execute("SELECT MAX(created) FROM backups").fetchone()
        return row[0] if row and row[0] else None
