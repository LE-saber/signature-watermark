import json
import os
from pathlib import Path
import subprocess
import sys


def test_gui_initializes_all_pages_and_exits(tmp_path):
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run([sys.executable, str(root / "app.py"), "--gui-smoke-test", str(tmp_path)],
                            cwd=root, env=env, capture_output=True, text=True, timeout=30)
    report = json.loads((tmp_path / "gui-smoke.json").read_text(encoding="utf-8"))
    assert result.returncode == 0, (report, result.stderr)
    assert report["ok"] and report["pages"] == 6
    assert report["platform"] == "offscreen"


def test_missing_qtcore_is_reported_as_a_failed_startup(tmp_path, monkeypatch):
    from app import gui_smoke_test

    monkeypatch.setitem(sys.modules, "PySide6.QtCore", None)
    assert gui_smoke_test(tmp_path) == 1
    report = json.loads((tmp_path / "gui-smoke.json").read_text(encoding="utf-8"))
    assert report["ok"] is False and "QtCore" in report["error"]
