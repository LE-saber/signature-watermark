import json
import string

import pytest

from sigwm import i18n


def _fields(s):
    return sorted(f for _, f, _, _ in string.Formatter().parse(s) if f is not None)


@pytest.mark.parametrize("lang", [c for c in i18n.LANGUAGES if c != i18n.SOURCE])
def test_catalog_complete_and_placeholders_match(lang):
    import tools.i18n.build as b  # noqa: PLC0415
    cat = json.loads((i18n.LOCALE_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    for key in b.code_keys():
        assert key in cat, f"{lang} missing {key!r}"
        assert _fields(cat[key]) == _fields(key), f"{lang}: {key!r}"


def test_tr_switches_language_and_formats():
    try:
        i18n.set_language("en")
        assert i18n.tr("設定") == "Settings"
        assert i18n.tr("已匯出 {n} 條記錄", n=3) == "Exported 3 records"
        i18n.set_language("ar")
        assert i18n.is_rtl()
    finally:
        i18n.set_language(i18n.SOURCE)
    assert i18n.tr("設定") == "設定"


def test_detect_returns_supported_code(monkeypatch):
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert i18n.detect() in i18n.LANGUAGES
