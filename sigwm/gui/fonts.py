"""Font choice per platform and UI language.

- macOS: the system UI font (SF Pro) plus the system CJK faces. SF Pro may not be
  redistributed, but calling the copy macOS ships is fine.
- Windows / Linux: bundled Inter (OFL), the open typeface closest to SF Pro,
  with the platform's best CJK face for the UI language as fallback.
- Han characters use the face for the UI language, so Japanese UI gets Japanese
  glyph shapes and Simplified Chinese gets mainland shapes.
- Arabic uses bundled Noto Sans Arabic.
- IDs and paths use bundled IBM Plex Mono.

Bundled fonts live in sigwm/fonts; the Linux build also adds Noto Sans CJK there.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"

CJK = {
    "darwin": {"zh_Hant": ["PingFang TC"], "zh_Hans": ["PingFang SC"], "ja": ["Hiragino Sans", "Hiragino Kaku Gothic ProN"],
               "ko": ["Apple SD Gothic Neo"]},
    "win32": {"zh_Hant": ["Microsoft JhengHei UI", "Microsoft JhengHei"], "zh_Hans": ["Microsoft YaHei UI", "Microsoft YaHei"],
              "ja": ["Yu Gothic UI", "Meiryo UI", "Meiryo"], "ko": ["Malgun Gothic"]},
    "linux": {"zh_Hant": ["Noto Sans CJK TC", "Source Han Sans TC"], "zh_Hans": ["Noto Sans CJK SC", "Source Han Sans SC"],
              "ja": ["Noto Sans CJK JP", "Source Han Sans JP"], "ko": ["Noto Sans CJK KR", "Source Han Sans KR"]},
}
# Order of the other CJK faces after the one for the UI language (for mixed-script data such as file names).
CJK_ORDER = ["zh_Hant", "zh_Hans", "ja", "ko"]

_loaded: set[str] = set()


def load_bundled() -> list[str]:
    for f in sorted(FONT_DIR.rglob("*")):
        if f.suffix.lower() in (".ttf", ".otf", ".ttc") and str(f) not in _loaded:
            QFontDatabase.addApplicationFont(str(f))
            _loaded.add(str(f))
    return sorted(QFontDatabase.families())


def _platform() -> str:
    return sys.platform if sys.platform in ("darwin", "win32") else "linux"


def ui_families(lang: str) -> list[str]:
    plat = _platform()
    available = set(QFontDatabase.families())
    cjk_map = CJK[plat]
    cjk = list(cjk_map.get(lang, []))
    for other in CJK_ORDER:
        if other != lang:
            cjk += cjk_map[other]
    if plat == "darwin":
        latin = [QFontDatabase.systemFont(QFontDatabase.GeneralFont).family()]
    else:
        latin = ["Inter"]
    generic = ["Segoe UI Variable Text", "Segoe UI"] if plat == "win32" else ["Noto Sans", "DejaVu Sans"]
    arabic = ["Noto Sans Arabic"]
    if lang == "ar":
        fams = arabic + latin + cjk + generic
    else:
        # Inter for Latin/Cyrillic/Greek, then the UI language's CJK face (so CJK punctuation
        # comes from it, not from a generic font), then the rest
        fams = latin + cjk + arabic + generic
    out = [f for f in dict.fromkeys(fams) if f in available or plat == "darwin"]
    return out or [QFontDatabase.systemFont(QFontDatabase.GeneralFont).family()]


def mono_families(lang: str) -> list[str]:
    return ["IBM Plex Mono", "Menlo", "Consolas", "DejaVu Sans Mono"] + ui_families(lang)


def ui_pixel_size(lang: str) -> int:
    return 14 if lang == "ar" else 13


def app_font(lang: str) -> QFont:
    f = QFont()
    f.setFamilies(ui_families(lang))
    f.setPixelSize(ui_pixel_size(lang))
    f.setHintingPreference(QFont.PreferNoHinting if _platform() != "win32" else QFont.PreferVerticalHinting)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def css_list(families: list[str]) -> str:
    return ", ".join(f'"{f}"' for f in families)
