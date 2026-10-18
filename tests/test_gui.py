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


def test_background_controls_preview_and_actual_export(tmp_path):
    root = Path(__file__).resolve().parent.parent
    script = r'''
import sys,traceback
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from sigwm import core
from sigwm.storage import Store
from sigwm.gui.page_embed import EmbedPage
from tests.test_background import paper_signature
folder=Path(sys.argv[1])
path=folder/'on-paper.png'
paper_signature().save(path)
store=Store(folder/'data', True)
app=QApplication([])
page=EmbedPage(store,lambda:'gui-background-test-password',lambda _msg:None)
page.add_paths([path])
page._render_preview()
item=page.items[0]
assert item.background_removed and np.asarray(item.small.getchannel('A'))[0,0]==0
page.background_cb.setChecked(False)
page._render_preview()
assert not item.background_removed and item.small.getchannel('A').getextrema()==(255,255)
page.background_cb.setChecked(True)
page._render_preview()
item.status='ok'
item.out='previous.png'
page._set_mode('feathered')
assert item.status=='wait' and not item.out
page.run()
def check():
    if page.job is not None:
        QTimer.singleShot(100,check)
        return
    try:
        assert item.status=='ok',item.error
        record=store.records()[0]
        out=Image.open(record.out_path)
        assert np.asarray(out.getchannel('A'))[0,0]==0
        assert core.extract(out,'gui-background-test-password').text==record.short_id
        assert record.params['remove_background'] is True
        assert store.settings.remove_background is True
        app.exit(0)
    except Exception:
        traceback.print_exc()
        app.exit(1)
QTimer.singleShot(100,check)
QTimer.singleShot(20000,lambda:app.exit(2))
code=app.exec()
store.close()
raise SystemExit(code)
'''
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], cwd=root,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, (result.stdout, result.stderr)
