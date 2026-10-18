"""Small reusable widgets."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Qt, Signal, QThreadPool
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QProgressBar, QSizePolicy, QVBoxLayout, QWidget)

from . import theme
from ..i18n import tr


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    qimg = QImage(img.tobytes(), img.width, img.height, 4 * img.width, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


def fmt_bytes(n: int | float) -> str:
    n = float(n)
    if n < 1024 * 1024:
        return f"{max(1, round(n / 1024)) if n else 0} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


def bold_width(text: str, delta_px: int = 0) -> int:
    """Width of text in the bold UI font (selected nav items and segments are bold)."""
    from PySide6.QtGui import QFont, QFontMetrics
    from PySide6.QtWidgets import QApplication
    f = QFont(QApplication.font())
    f.setPixelSize(theme.BASE["px"] + delta_px)
    f.setWeight(QFont.DemiBold)
    return QFontMetrics(f).horizontalAdvance(text)


def label(text: str = "", muted: bool = False, mono: bool = False, wrap: bool = False, bold: bool = False) -> QLabel:
    lb = QLabel(text)
    if muted:
        lb.setProperty("muted", True)
    if mono:
        lb.setProperty("mono", True)
    if bold:
        lb.setStyleSheet("font-weight:600;")
    lb.setWordWrap(wrap)
    lb.setTextInteractionFlags(Qt.TextSelectableByMouse if mono else Qt.NoTextInteraction)
    return lb


class Chip(QLabel):
    def __init__(self, text: str = "", kind: str = ""):
        super().__init__()
        self.set(text, kind)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set(self, text: str, kind: str = ""):
        self.setText(text)
        self.setStyleSheet(theme.chip_style(kind))
        self.setVisible(bool(text))


class Panel(QFrame):
    """Bordered box with a header row, a body and an optional run bar."""

    def __init__(self, title: str = "", right: QWidget | None = None):
        super().__init__()
        self.setObjectName("panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        if title or right:
            head = QFrame()
            head.setObjectName("panelHead")
            hl = QHBoxLayout(head)
            hl.setContentsMargins(14, 9, 14, 9)
            self.title = QLabel(title)
            self.title.setObjectName("panelTitle")
            self.sub = label("", muted=True)
            hl.addWidget(self.title)
            hl.addWidget(self.sub)
            hl.addStretch(1)
            if right:
                hl.addWidget(right)
            lay.addWidget(head)
        self.body = QWidget()
        self.bl = QVBoxLayout(self.body)
        self.bl.setContentsMargins(14, 14, 14, 14)
        self.bl.setSpacing(12)
        lay.addWidget(self.body, 1)
        self._lay = lay

    def add_runbar(self) -> tuple[QProgressBar, QLabel, QHBoxLayout]:
        bar = QFrame()
        bar.setObjectName("runbar")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(4)
        prog = QProgressBar()
        prog.setTextVisible(False)
        prog.setRange(0, 100)
        prog.setValue(0)
        txt = label(tr('就緒'), muted=True)
        col.addWidget(prog)
        col.addWidget(txt)
        hl.addLayout(col, 1)
        self._lay.addWidget(bar)
        return prog, txt, hl


class DropZone(QFrame):
    dropped = Signal(list)

    def __init__(self, title: str, hint: str, buttons: list[tuple[str, Callable]]):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        col = QVBoxLayout(self)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(4)
        t = QLabel(title)
        t.setStyleSheet("font-weight:600;")
        col.addWidget(t)
        col.addWidget(label(hint, muted=True, wrap=True))
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 0)
        for text, fn in buttons:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        col.addLayout(row)

    def _set_over(self, on: bool):
        self.setProperty("over", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_over(True)

    def dragLeaveEvent(self, e):
        self._set_over(False)

    def dropEvent(self, e):
        self._set_over(False)
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)


class PathPicker(QWidget):
    """Read-only path field + 瀏覽… that opens the system folder (or file) dialog."""
    changed = Signal(str)

    def __init__(self, title: str, folder: bool = True, filter_: str = ""):
        super().__init__()
        self.title, self.folder, self.filter_ = title, folder, filter_
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setReadOnly(True)
        b = QPushButton(tr('瀏覽…'))
        b.clicked.connect(self.browse)
        hl.addWidget(self.edit, 1)
        hl.addWidget(b)

    def path(self) -> str:
        return self.edit.text()

    def set_path(self, p: str):
        self.edit.setText(p)
        self.edit.setCursorPosition(0)

    def browse(self):
        start = self.path() or str(Path.home())
        if self.folder:
            p = QFileDialog.getExistingDirectory(self, self.title, start)
        else:
            p, _ = QFileDialog.getOpenFileName(self, self.title, str(Path(start).parent if Path(start).is_file() else start), self.filter_)
        if p:
            self.set_path(p)
            self.changed.emit(p)


class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], current: str):
        super().__init__()
        self.setObjectName("segBox")
        hl = QHBoxLayout(self)
        hl.setContentsMargins(3, 3, 3, 3)
        hl.setSpacing(2)
        self.group = QButtonGroup(self)
        for key, text in items:
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(key == current)
            b.setProperty("key", key)
            b.setMinimumWidth(bold_width(text, -1) + 24)
            self.group.addButton(b)
            hl.addWidget(b)
        self.group.buttonClicked.connect(lambda b: self.changed.emit(b.property("key")))


class CheckRow(QFrame):
    """A selectable row: checkbox, title + subtitle, right-aligned info."""
    toggled = Signal(bool)

    def __init__(self, title: str, sub: str = "", checked: bool = False):
        super().__init__()
        self.setObjectName("check")
        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 9, 12, 9)
        hl.setSpacing(10)
        self.box = QCheckBox()
        self.box.setChecked(checked)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.t = QLabel(title)
        self.t.setStyleSheet("font-weight:600;")
        self.s = label(sub, muted=True, wrap=True)
        col.addWidget(self.t)
        col.addWidget(self.s)
        self.right = QVBoxLayout()
        self.right.setSpacing(3)
        self.size = label("", muted=True, mono=True)
        self.size.setAlignment(Qt.AlignRight)
        self.chip = Chip()
        self.right.addWidget(self.size, 0, Qt.AlignRight)
        self.right.addWidget(self.chip, 0, Qt.AlignRight)
        hl.addWidget(self.box)
        hl.addLayout(col, 1)
        hl.addLayout(self.right)
        self.box.toggled.connect(self._on)
        self._on(checked)

    def _on(self, v: bool):
        self.setProperty("on", v)
        self.style().unpolish(self)
        self.style().polish(self)
        self.toggled.emit(v)

    def mousePressEvent(self, e):
        if self.box.isEnabled():
            self.box.toggle()

    def checked(self) -> bool:
        return self.box.isChecked() and self.box.isEnabled()

    def set_enabled(self, on: bool):
        if not on:
            self.box.setChecked(False)
        self.box.setEnabled(on)
        self.setEnabled(on)


# ---------------------------------------------------------------- background jobs

class _Signals(QObject):
    progress = Signal(object)
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    """Run fn(report, is_cancelled) in the thread pool; report(x) emits progress."""

    def __init__(self, fn: Callable):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.cancelled = False
        self.setAutoDelete(False)

    def run(self):
        try:
            res = self.fn(self.signals.progress.emit, lambda: self.cancelled)
            self.signals.done.emit(res)
        except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
            import traceback
            traceback.print_exc()
            self.signals.failed.emit(str(exc))

    def cancel(self):
        self.cancelled = True


_jobs: set[Job] = set()


def start_job(fn: Callable, on_progress=None, on_done=None, on_failed=None) -> Job:
    job = Job(fn)
    if on_progress:
        job.signals.progress.connect(on_progress)
    if on_done:
        job.signals.done.connect(on_done)
    if on_failed:
        job.signals.failed.connect(on_failed)
    job.signals.done.connect(lambda _r: _jobs.discard(job))
    job.signals.failed.connect(lambda _r: _jobs.discard(job))
    _jobs.add(job)
    QThreadPool.globalInstance().start(job)
    return job
