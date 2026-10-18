"""Batch operations used by the GUI and the CLI (no Qt here)."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import core
from .storage import Record, Store, now_iso
from .i18n import tr

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class EmbedOutcome:
    ok: bool
    src: Path
    record: Record | None = None
    out_path: Path | None = None
    error: str = ""
    warnings: tuple[str, ...] = ()


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 10_000):
        cand = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not cand.exists():
            return cand
    raise core.WatermarkError(tr('輸出資料夾裏同名文件太多'))


def output_name(pattern: str, sig_id: str, short: str, src: Path) -> str:
    name = (pattern or "SIG-{date}-{short}").format(
        date=datetime.now().strftime("%Y%m%d"), short=short, id=sig_id, src=src.stem)
    name = "".join(c for c in name if c not in '<>:"/\\|?*').strip() or sig_id
    return name + ".png"


def embed_file(store: Store, src: Path, password: str, params: core.CarrierParams, purpose: str,
               out_dir: Path | None = None, retries: int = 3) -> EmbedOutcome:
    src = Path(src)
    try:
        img, warnings = core.load_signature(src)
        if not params.remove_background and img.getchannel("A").getextrema()[0] == 255:
            warnings.append(tr('原圖不是透明底，建議先去背景'))
        last_err: Exception | None = None
        for _ in range(retries):
            short = core.new_short_id()
            if store.record_by_short(short):
                continue
            sig_id = f"SIG-{datetime.now().strftime('%Y%m%d')}-{short}"
            try:
                res = core.embed_signature(img, password, params, sig_id, short, self_check=store.settings.self_check)
                break
            except core.SelfCheckError as exc:
                last_err = exc
        else:
            raise last_err or core.WatermarkError(tr('無法生成不重複的 ID'))

        out_dir = Path(out_dir or store.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = _unique(out_dir / output_name(store.settings.naming, sig_id, short, src))
        res.image.save(out_path, format="PNG")

        upload = _unique(store.kind_dir("uploads") / f"{sig_id}{src.suffix.lower() or '.png'}")
        shutil.copy2(src, upload)
        store.track(upload, "uploads")
        if out_path.resolve().is_relative_to(store.root.resolve()):
            store.track(out_path, "outputs")

        rec = Record(
            id=sig_id, short_id=short, purpose=purpose, mode=params.mode, width=res.width, height=res.height,
            sig_bbox=res.sig_bbox, params={"padding": params.padding, "alpha": params.alpha,
                                           "feather": params.feather, "texture": params.texture,
                                           "remove_background": params.remove_background,
                                           "background_threshold": params.background_threshold},
            src_name=src.name, src_sha256=core.sha256_file(src), out_path=str(out_path),
            out_sha256=core.sha256_file(out_path), created=now_iso(), format=core.FORMAT,
            extra={"upload": str(upload)})
        store.add_record(rec)
        return EmbedOutcome(True, src, rec, out_path, warnings=tuple(warnings))
    except core.WatermarkError as exc:
        return EmbedOutcome(False, src, error=str(exc))
    except OSError as exc:
        return EmbedOutcome(False, src, error=tr('文件讀寫失敗：{exc}', exc=exc))


def expand_inputs(paths: list[Path]) -> list[Path]:
    """Files as given; folders are walked for images."""
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out.extend(sorted(q for q in p.rglob("*") if q.suffix.lower() in IMAGE_EXT and q.is_file()))
        elif p.is_file():
            out.append(p)
    seen, uniq = set(), []
    for p in out:
        k = str(p.resolve())
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def import_legacy(store: Store, folder: Path) -> tuple[int, int]:
    """Import records written by the old signature_watermark_blind.py (out/watermark/SIG-*.txt).

    Returns (imported, skipped). Old records have no signature bbox, so they can be
    traced when the signature image itself is checked, not when located on a page.
    """
    folder = Path(folder)
    meta_dir = folder / "watermark" if (folder / "watermark").is_dir() else folder
    img_dir = meta_dir.parent / "images"
    added = skipped = 0
    for txt in sorted(meta_dir.glob("SIG-*.txt")):
        meta = {}
        for raw in txt.read_text(encoding="utf-8-sig").splitlines():
            if "=" in raw:
                k, v = raw.split("=", 1)
                meta[k.strip()] = v.strip()
        if meta.get("FORMAT") != "SIG-BLIND-WM-1" or not meta.get("SHORT_ID"):
            skipped += 1
            continue
        if store.record_by_short(meta["SHORT_ID"]):
            skipped += 1
            continue
        img = img_dir / f"{meta['ID']}.png"
        store.add_record(Record(
            id=meta["ID"], short_id=meta["SHORT_ID"], purpose=meta.get("PURPOSE", ""), mode=meta.get("BACKGROUND", ""),
            width=int(meta.get("WIDTH", 0) or 0), height=int(meta.get("HEIGHT", 0) or 0), sig_bbox=(0, 0, 0, 0),
            params={k.lower(): meta[k] for k in ("CARRIER_PADDING", "CARRIER_ALPHA", "CARRIER_FEATHER", "TEXTURE_STRENGTH") if k in meta},
            src_name="signature.png", src_sha256=meta.get("SOURCE_SHA256", ""), out_path=str(img) if img.exists() else "",
            out_sha256=meta.get("OUTPUT_SHA256", ""), created=meta.get("CREATED", ""), format="SIG-BLIND-WM-1",
            wm_shape=int(meta.get("WM_SHAPE", 63) or 63), extra={"legacy": str(txt)}))
        added += 1
    return added, skipped
