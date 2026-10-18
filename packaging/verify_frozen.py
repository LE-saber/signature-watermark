"""Check a frozen GUI with no development tools in its DLL search path."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve()
    env = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
                 "QML_IMPORT_PATH", "QML2_IMPORT_PATH"):
        env.pop(name, None)
    startup = None
    if sys.platform == "win32":
        windows = Path(env["SYSTEMROOT"])
        env["PATH"] = os.pathsep.join((str(windows / "System32"), str(windows)))
        env["QT_QPA_PLATFORM"] = "windows"
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
    else:
        env["QT_QPA_PLATFORM"] = "offscreen"
    with tempfile.TemporaryDirectory(prefix="sigwm-gui-smoke-") as tmp:
        folder = Path(tmp)
        try:
            result = subprocess.run([str(executable), "--gui-smoke-test", str(folder)], cwd=folder,
                                    env=env, startupinfo=startup, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=60)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Frozen GUI did not finish startup verification within 60 seconds") from exc
        report_path = folder / "gui-smoke.json"
        if not report_path.exists():
            raise RuntimeError(f"Frozen GUI produced no report (exit {result.returncode})\n"
                               f"{result.stdout}\n{result.stderr}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if result.returncode or not report.get("ok") or report.get("pages") != 6:
            raise RuntimeError(f"Frozen GUI startup failed: {report}")
        if report.get("platform") != env["QT_QPA_PLATFORM"]:
            raise RuntimeError(f"Unexpected Qt platform plugin: {report}")
        print("Frozen GUI startup verified:", json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
