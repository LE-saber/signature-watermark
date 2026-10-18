"""UI translations.

Source strings are the Traditional Chinese texts written in the code; each other
language has a JSON catalog in sigwm/locales/<code>.json mapping source -> text.
A missing entry falls back to the source string, so an incomplete catalog never
breaks the UI (tests/test_i18n.py checks that catalogs are complete).

Placeholders use str.format names: tr("已加入 {added} 個文件", added=3).
"""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path

LANGUAGES = {                  # code -> name shown in its own language
    "zh_Hant": "繁體中文",
    "zh_Hans": "简体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "fr": "Français",
    "es": "Español",
    "ru": "Русский",
    "ar": "العربية",
}
SOURCE = "zh_Hant"
RTL = {"ar"}
LOCALE_DIR = Path(__file__).resolve().parent / "locales"

_lang = SOURCE
_catalog: dict[str, str] = {}


def load_catalog(code: str) -> dict[str, str]:
    if code == SOURCE:
        return {}
    path = LOCALE_DIR / f"{code}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_language(code: str) -> str:
    global _lang, _catalog
    if code not in LANGUAGES:
        code = detect()
    _lang = code
    _catalog = load_catalog(code)
    return code


def language() -> str:
    return _lang


def is_rtl() -> bool:
    return _lang in RTL


def detect() -> str:
    """Best guess from the OS locale; English when nothing matches."""
    names = [os.environ.get(k, "") for k in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")]
    try:
        names.append(locale.getlocale()[0] or "")
    except ValueError:
        pass
    try:
        from PySide6.QtCore import QLocale
        names.insert(0, QLocale.system().name())
        names.insert(0, (QLocale.system().uiLanguages() or [""])[0])
    except Exception:  # noqa: BLE001 - Qt not available (CLI)
        pass
    for raw in names:
        n = raw.replace("-", "_").lower()
        if not n:
            continue
        if n.startswith("zh"):
            if any(t in n for t in ("hant", "_tw", "_hk", "_mo", "traditional")):
                return "zh_Hant"
            return "zh_Hans"
        for code in ("ja", "ko", "fr", "es", "ru", "ar", "en"):
            if n.startswith(code):
                return code
    return "en"


def tr(text: str, **kw) -> str:
    out = _catalog.get(text, text)
    if kw:
        try:
            return out.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text.format(**kw)
    return out
