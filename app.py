"""SigWatermark entry point.

Double-click (no arguments) opens the window. Command line:

    SigWatermark embed <files or folders> [--mode feathered_texture] [--purpose 文字] [--out 資料夾]
    SigWatermark trace <files>
    SigWatermark --data-dir <folder> ...   use another data folder
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from sigwm.i18n import set_language, tr


def _cli(argv: list[str]) -> int:
    from sigwm import core, secret, service, trace
    from sigwm.storage import Store

    set_language("")
    ap = argparse.ArgumentParser(prog="SigWatermark")
    ap.add_argument("--data-dir")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("embed", help=tr('批量加水印'))
    e.add_argument("paths", nargs="+")
    e.add_argument("--mode", default=None, choices=core.MODES)
    e.add_argument("--purpose", default="signature-use")
    e.add_argument("--out")
    t = sub.add_parser("trace", help=tr('溯源文件、照片或圖片'))
    t.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)

    store = Store(Path(a.data_dir), True) if a.data_dir else Store()
    set_language(store.settings.language)
    pw = secret.get_password(store)
    if len(pw) < 12:
        print(tr('尚未設定水印密碼，請先打開程式在「設定」裏設定。'), file=sys.stderr)
        return 2
    if a.cmd == "embed":
        st = store.settings
        p = core.CarrierParams(a.mode or st.mode, st.padding, st.alpha, st.feather, st.texture)
        fails = 0
        for f in service.expand_inputs([Path(x) for x in a.paths]):
            r = service.embed_file(store, f, pw, p, a.purpose, Path(a.out) if a.out else None)
            if r.ok:
                print(f"OK    {f.name} -> {r.out_path}  {r.record.id}")
            else:
                fails += 1
                print(f"FAIL  {f.name}: {r.error}")
        return 1 if fails else 0
    for f in a.paths:
        res = trace.analyze(store, pw, Path(f))
        print(f"{f}: {res.error}" if res.error else tr('{f}: {v} 個簽名', f=f, v=len(res.hits)))
        for h in res.hits:
            who = tr('{id}（{purpose}）', id=h.record.id, purpose=h.record.purpose) if h.record else "-"
            print(tr('  第 {page} 頁  {kind:<5}  {bits}/63  {who}', page=h.page, kind=h.kind, bits=h.bits, who=who))
    return 0


def _attach_console() -> None:
    """The Windows build is a GUI app with no console; print to the calling terminal if there is one."""
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                sys.stderr = sys.stdout
        except OSError:
            pass
    import os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = sys.stdout


def main(smoke_dir: Path | None = None) -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("embed", "trace", "--data-dir", "-h", "--help"):
        _attach_console()
        try:
            return _cli(sys.argv[1:])
        except SystemExit as exc:
            return int(exc.code or 0)

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from sigwm import i18n
    from sigwm.storage import Store

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0]] if smoke_dir else sys.argv)
    app.setApplicationName("SigWatermark")
    app.setStyle("Fusion")
    icon = Path(__file__).resolve().parent / "packaging" / "icon.png"
    if getattr(sys, "frozen", False):
        icon = Path(getattr(sys, "_MEIPASS", ".")) / "packaging" / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    try:
        store = Store(smoke_dir / "data", True) if smoke_dir else Store()
    except Exception as exc:  # noqa: BLE001
        if smoke_dir:
            raise
        i18n.set_language("")
        QMessageBox.critical(None, "SigWatermark", tr('無法打開資料目錄：{exc}', exc=exc))
        return 1
    lang = i18n.set_language(store.settings.language)
    # GUI modules build some labels at import time, so import them after the language is set
    from sigwm.gui import theme
    from sigwm.gui.main_window import MainWindow
    theme.apply(app, lang)
    win = MainWindow(store)
    win.show()
    if smoke_dir:
        from PySide6.QtCore import QTimer, qVersion

        def check_window():
            try:
                for key in ("embed", "trace", "records", "backup", "clean", "settings"):
                    win.go(key)
                if win.stack.count() != 6 or not win.isVisible():
                    raise RuntimeError("The application window did not initialize")
                report = {"ok": True, "qt_version": qVersion(), "platform": app.platformName(),
                          "pages": win.stack.count()}
                (smoke_dir / "gui-smoke.json").write_text(json.dumps(report), encoding="utf-8")
                app.quit()
            except Exception as exc:  # noqa: BLE001 - report asynchronous Qt failures to the caller
                (smoke_dir / "gui-smoke.json").write_text(
                    json.dumps({"ok": False, "error": str(exc)}), encoding="utf-8")
                app.exit(1)

        QTimer.singleShot(150, check_window)
    rc = app.exec()
    store.close()
    return rc


def gui_smoke_test(folder: Path) -> int:
    """Exercise normal GUI startup without reading the user's data or keyring."""
    folder.mkdir(parents=True, exist_ok=True)
    try:
        from sigwm import secret
        secret._keyring = lambda: None
        return main(folder)
    except Exception:  # noqa: BLE001 - include early DLL import failures in a machine-readable report
        import traceback
        (folder / "gui-smoke.json").write_text(
            json.dumps({"ok": False, "error": traceback.format_exc()}), encoding="utf-8")
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--gui-smoke-test":
        sys.exit(gui_smoke_test(Path(sys.argv[2])))
    sys.exit(main())
