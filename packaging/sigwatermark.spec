# PyInstaller spec — run via packaging/build.py, which also makes the portable archive.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from sigwm import __version__

ICON = ROOT / "packaging" / "icon.png"   # PyInstaller converts it to .ico / .icns (needs Pillow)

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    datas=[(str(ICON), "packaging"), (str(ROOT / "sigwm" / "vendor" / "bwm" / "LICENSE"), "licenses/blind_watermark"),
           (str(ROOT / "sigwm" / "fonts"), "sigwm/fonts"), (str(ROOT / "sigwm" / "locales"), "sigwm/locales")],
    hiddenimports=["keyring.backends.Windows", "keyring.backends.macOS", "keyring.backends.SecretService",
                   "keyring.backends.libsecret", "keyring.backends.kwallet"],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest", "blind_watermark", "docx", "cv2",
              "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtSql", "PySide6.QtTest",
              "PySide6.QtOpenGL", "PySide6.QtDBus"] if sys.platform != "linux" else
             ["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest", "blind_watermark", "docx", "cv2",
              "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtSql", "PySide6.QtTest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SigWatermark",
    console=False,
    icon=str(ICON),
    target_arch=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SigWatermark")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SigWatermark.app",
        icon=str(ICON),
        bundle_identifier="app.sigwatermark.desktop",
        info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": __version__,
                    "LSApplicationCategoryType": "public.app-category.productivity"},
    )
