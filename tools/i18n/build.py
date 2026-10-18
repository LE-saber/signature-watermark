"""Build sigwm/locales/<lang>.json from the translation tables.

    python tools/i18n/build.py

Fails when a tr() string in the code has no row, or a translation's placeholders
differ from the source.
"""
from __future__ import annotations

import ast
import json
import string
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
COLS = ["zh_Hans", "en", "ja", "ko", "fr", "es", "ru", "ar"]


def code_keys() -> list[str]:
    keys: list[str] = []
    for p in sorted(list((ROOT / "sigwm").rglob("*.py")) + [ROOT / "app.py"]):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "tr" and n.args and isinstance(n.args[0], ast.Constant):
                if n.args[0].value not in keys:
                    keys.append(n.args[0].value)
    return keys


def fields(s: str) -> list[str]:
    return sorted(f for _, f, _, _ in string.Formatter().parse(s) if f is not None)


def main() -> int:
    rows = {}
    for t in sorted(HERE.glob("table*.py")):
        ns: dict = {}
        exec(t.read_text(encoding="utf-8"), ns)
        for row in ns["ROWS"]:
            if len(row) != 1 + len(COLS):
                print(f"{t.name}: wrong column count: {row[0]!r}")
                return 1
            rows[row[0]] = row[1:]
    keys = code_keys()
    errors = [f"missing translation: {k!r}" for k in keys if k not in rows]
    for k, vals in rows.items():
        for lang, v in zip(COLS, vals):
            if fields(v) != fields(k):
                errors.append(f"{lang}: placeholders differ for {k!r}: {v!r}")
    unused = [k for k in rows if k not in keys]
    if errors:
        print("\n".join(errors))
        return 1
    out = ROOT / "sigwm" / "locales"
    out.mkdir(exist_ok=True)
    for i, lang in enumerate(COLS):
        cat = {k: rows[k][i] for k in keys}
        (out / f"{lang}.json").write_text(json.dumps(cat, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(keys)} strings x {len(COLS)} languages written" + (f"; unused rows: {unused}" if unused else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
