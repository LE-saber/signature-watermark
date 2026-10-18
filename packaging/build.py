"""Build the portable archive for the current OS.

    python packaging/build.py            -> dist/SigWatermark-<version>-<os>-<arch>.zip / .tar.gz

PyInstaller cannot cross-compile: run this on Windows, macOS and Linux (CI does).
"""
from __future__ import annotations

import os
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

Start
  Extract the entire archive before launching. No Python installation is needed.
  Windows : Double-click SigWatermark\\SigWatermark.exe.
  macOS   : Open SigWatermark.app. The app is unsigned and not notarized.
  Linux   : Run ./SigWatermark/SigWatermark.
            Some desktop installations need xcb runtime libraries; see README.md.
  Keep the application and all its support files together.

Data
  Portable mode stores settings, signing records and images in data/ next to the
  application. If that location is not writable, the user data folder is used.
  Check Settings for the active location.

Watermark password
  Use Generate and save in Settings, or enter at least 12 characters before embedding.
  Tracing requires the same password and the corresponding signing records.
  Use Backup and restore when moving computers. Including the watermark password
  in a backup requires an encrypted backup.

Command line (optional)
  SigWatermark embed <images or folders> [--mode feathered_texture] [--purpose text]
  SigWatermark trace <PDF/Word/images>

Languages
  README.md is in English. See README.zh-CN.md for Simplified Chinese and
  README.zh-TW.md for Traditional Chinese. The UI follows the system language
  by default and can be changed in Settings.

Third-party components
  Watermark core adapted from guofei9987/blind_watermark (MIT).
  Bundled fonts: Inter, Noto Sans Arabic, IBM Plex Mono and, on Linux,
  Noto Sans CJK (SIL OFL). License texts are included in licenses/.
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


def build_environment() -> dict[str, str]:
    env = os.environ.copy()
    if sys.platform == "win32":
        # Dependency scanning must not pick up unrelated DLLs from tools such as
        # Poppler. Its ICU has the same filename as Windows ICU but different exports.
        windows = Path(env["SYSTEMROOT"])
        paths = (Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
                 windows / "System32", windows)
        env["PATH"] = os.pathsep.join(str(p) for p in dict.fromkeys(paths) if p.is_dir())
    return env


def main() -> int:
    fetch_cjk_for_linux()
    dist, build = ROOT / "dist", ROOT / "build"
    shutil.rmtree(dist, ignore_errors=True)
    shutil.rmtree(build, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(dist), "--workpath", str(build),
                    str(ROOT / "packaging" / "sigwatermark.spec")], check=True, env=build_environment())

    stage = dist / "stage"
    stage.mkdir()
    if sys.platform == "darwin":
        shutil.copytree(dist / "SigWatermark.app", stage / "SigWatermark.app", symlinks=True)
    else:
        shutil.copytree(dist / "SigWatermark", stage / "SigWatermark", symlinks=True)
    (stage / "README.txt").write_text(README.format(version=__version__), encoding="utf-8")
    for name in ("README.md", "README.zh-CN.md", "README.zh-TW.md"):
        shutil.copy2(ROOT / name, stage / name)
    shutil.copytree(ROOT / "docs" / "images", stage / "docs" / "images")
    shutil.copy2(ROOT / "docs" / "VALIDATION.md", stage / "docs" / "VALIDATION.md")
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
