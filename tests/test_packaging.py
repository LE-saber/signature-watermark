import os
from pathlib import Path
import runpy
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DLL search path regression")
def test_windows_build_excludes_unrelated_tools_from_dll_search(tmp_path, monkeypatch):
    poppler = tmp_path / "poppler" / "Library" / "bin"
    poppler.mkdir(parents=True)
    monkeypatch.setenv("PATH", str(poppler) + os.pathsep + os.environ["PATH"])
    script = Path(__file__).resolve().parent.parent / "packaging" / "build.py"
    env = runpy.run_path(str(script))["build_environment"]()
    assert str(poppler) not in env["PATH"].split(os.pathsep)
    assert str(Path(os.environ["SYSTEMROOT"]) / "System32") in env["PATH"].split(os.pathsep)
