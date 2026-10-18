"""Build the portable archive for the current OS.

    python packaging/build.py            -> dist/SigWatermark-<version>-<os>-<arch>.zip / .tar.gz

PyInstaller cannot cross-compile: run this on Windows, macOS and Linux (CI does).
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sigwm import __version__  # noqa: E402

README = """SigWatermark {version}
=====================

啟動
  Windows : 解壓後雙擊 SigWatermark\\SigWatermark.exe
  macOS   : 解壓後雙擊 SigWatermark.app（第一次請按右鍵選「打開」）
  Linux   : 解壓後執行 SigWatermark/SigWatermark
            若提示缺少 xcb 相關庫，請安裝 libxcb-cursor0（Debian/Ubuntu）

資料位置
  預設為便攜模式：簽發記錄、輸出圖片和設定都存在程式旁邊的 data/ 資料夾，
  整個資料夾可以直接拷到別的電腦。若程式所在位置不能寫入（例如 macOS 從
  「下載」直接打開時），會自動改用使用者目錄，可在「設定」裏查看。

水印密碼
  第一次打開請在「設定」裏設定水印密碼（至少 12 個字元）。提取和溯源時必須
  使用同一個密碼。換電腦時請用「備份與恢復」帶走（可勾選同時備份水印密碼）。

命令列（可選）
  SigWatermark embed <圖片或資料夾> [--mode feathered_texture] [--purpose 用途]
  SigWatermark trace <PDF/Word/圖片>

第三方元件
  水印核心改寫自 guofei9987/blind_watermark（MIT）。
  字體：Inter、Noto Sans Arabic、IBM Plex Mono（Linux 版另含 Noto Sans CJK），均為 SIL OFL。
  授權全文見 licenses/。
"""


def os_tag() -> str:
    sysname = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = platform.machine().lower().replace("amd64", "x64").replace("x86_64", "x64").replace("aarch64", "arm64")
    return f"{sysname}-{arch}"


CJK_URL = "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/Variable/OTC/NotoSansCJK-VF.otf.ttc"


def fetch_cjk_for_linux() -> None:
    """Windows and macOS ship good CJK fonts; Linux distributions may not, so bundle Noto Sans CJK there."""
    if sys.platform in ("win32", "darwin"):
        return
    import urllib.request
    target = ROOT / "sigwm" / "fonts" / "cjk" / "NotoSansCJK-VF.otf.ttc"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        print("downloading Noto Sans CJK …")
        urllib.request.urlretrieve(CJK_URL, target)
    lic = target.parent / "LICENSE.txt"
    if not lic.exists():
        urllib.request.urlretrieve("https://github.com/notofonts/noto-cjk/raw/Sans2.004/LICENSE", lic)


def main() -> int:
    fetch_cjk_for_linux()
    dist, build = ROOT / "dist", ROOT / "build"
    shutil.rmtree(dist, ignore_errors=True)
    shutil.rmtree(build, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(dist), "--workpath", str(build),
                    str(ROOT / "packaging" / "sigwatermark.spec")], check=True)

    stage = dist / "stage"
    stage.mkdir()
    if sys.platform == "darwin":
        shutil.copytree(dist / "SigWatermark.app", stage / "SigWatermark.app", symlinks=True)
    else:
        shutil.copytree(dist / "SigWatermark", stage / "SigWatermark", symlinks=True)
    (stage / "使用說明.txt").write_text(README.format(version=__version__), encoding="utf-8")
    lic = stage / "licenses"
    lic.mkdir()
    shutil.copy2(ROOT / "sigwm" / "vendor" / "bwm" / "LICENSE", lic / "blind_watermark-LICENSE.txt")
    for ofl in (ROOT / "sigwm" / "fonts").rglob("*.txt"):
        shutil.copy2(ofl, lic / f"font-{ofl.parent.name}-{ofl.name}" if ofl.parent.name == "cjk" else lic / f"font-{ofl.name}")

    name = f"SigWatermark-{__version__}-{os_tag()}"
    if sys.platform == "darwin":
        out = dist / f"{name}.zip"
        # ditto keeps the .app's symlinks and permissions intact
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", str(stage), str(out)], check=True)
    elif sys.platform == "win32":
        out = dist / f"{name}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for p in sorted(stage.rglob("*")):
                zf.write(p, p.relative_to(stage))
    else:
        out = dist / f"{name}.tar.gz"
        with tarfile.open(out, "w:gz") as tf:
            for p in sorted(stage.iterdir()):
                tf.add(p, arcname=p.name)
    print(f"\nbuilt {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
