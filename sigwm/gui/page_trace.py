"""簽名溯源 page."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget)

from .. import trace
from ..storage import Store
from . import theme
from .widgets import Chip, DropZone, Panel, label, pil_to_pixmap, start_job
from ..i18n import tr

DOC_EXT = {".pdf", ".docx", ".docm", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class Doc:
    path: Path
    status: str = "wait"   # wait | run | done
    step: str = ""
    result: trace.TraceResult | None = None
    page: int = 1


class PageView(QWidget):
    """Shows one page preview with hit boxes; drag to select a region in manual mode."""
    selected = Signal(tuple)

    def __init__(self):
        super().__init__()
        self.pixmap = None
        self.hits: list[tuple[int, trace.Hit]] = []
        self.manual = False
        self._drag: tuple[QPoint, QPoint] | None = None
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_page(self, pixmap, hits):
        self.pixmap, self.hits = pixmap, hits
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        if not self.pixmap:
            return QSize(300, 400)
        w = max(240, self.width())
        return QSize(w, int(w * self.pixmap.height() / self.pixmap.width()))

    def hasHeightForWidth(self):
        return self.pixmap is not None

    def heightForWidth(self, w):
        return int(w * self.pixmap.height() / self.pixmap.width()) if self.pixmap else 400

    def _k(self) -> float:
        return self.width() / self.pixmap.width() if self.pixmap else 1.0

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if not self.pixmap:
            p.setPen(QColor(theme.T["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, tr('選擇左邊的文件'))
            return
        k = self._k()
        target = QRect(0, 0, self.width(), int(self.pixmap.height() * k))
        p.drawPixmap(target, self.pixmap)
        p.setPen(QPen(QColor(theme.T["line"]), 1))
        p.drawRect(target.adjusted(0, 0, -1, -1))
        for n, h in self.hits:
            col = QColor(theme.T["ok" if h.kind == "match" else "warn" if h.kind == "weak" else "bad"])
            pen = QPen(col, 2.5)
            if h.kind == "none":
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            x0, y0, x1, y1 = (int(v * k) for v in h.box)
            p.drawRect(QRect(QPoint(x0 - 3, y0 - 3), QPoint(x1 + 3, y1 + 3)))
            tag = QRect(x0 - 3, max(0, y0 - 22), 30, 18)
            p.fillRect(tag, col)
            p.setPen(QColor("#ffffff"))
            f = QFont(p.font())
            f.setBold(True)
            f.setPointSizeF(9)
            p.setFont(f)
            p.drawText(tag, Qt.AlignCenter, f"#{n}")
        if self._drag:
            p.setPen(QPen(QColor(theme.T["accent"]), 2, Qt.DashLine))
            p.drawRect(QRect(*self._drag).normalized())

    def mousePressEvent(self, e):
        if self.manual and self.pixmap:
            self._drag = (e.position().toPoint(), e.position().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._drag = (self._drag[0], e.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, e):
        if not self._drag:
            return
        r = QRect(*self._drag).normalized()
        self._drag = None
        self.update()
        if r.width() > 12 and r.height() > 8:
            k = self._k()
            self.selected.emit((int(r.left() / k), int(r.top() / k), int(r.right() / k), int(r.bottom() / k)))


class HitCard(QFrame):
    show_record = Signal(str)

    def __init__(self, n: int, h: trace.Hit):
        super().__init__()
        self.setObjectName("hitCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(label(tr('簽名 #{n} · 第 {page} 頁', n=n, page=h.page), bold=True))
        head.addStretch(1)
        chip = {"match": (tr('匹配'), "ok"), "weak": (tr('可能匹配'), "warn"), "none": (tr('無水印'), "bad")}[h.kind]
        head.addWidget(Chip(*chip))
        lay.addLayout(head)
        if h.crop is not None:
            thumb = h.crop.copy()
            thumb.thumbnail((260, 80))
            img = QLabel()
            img.setPixmap(pil_to_pixmap(thumb))
            img.setStyleSheet(f"border:1px solid {theme.T['line']}; border-radius:4px; background:#ffffff;")
            img.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            lay.addWidget(img)
        r = h.record
        if r:
            grid = QVBoxLayout()
            grid.setSpacing(2)
            for k, v, mono in ((tr('簽發 ID'), r.id, True), (tr('用途'), r.purpose, False), (tr('簽發時間'), r.created.replace("T", " ")[:19], True),
                               (tr('源文件'), r.src_name, False)):
                row = QHBoxLayout()
                kl = label(k, muted=True)
                kl.setFixedWidth(64)
                row.addWidget(kl)
                vl = label(v, mono=mono, wrap=True)
                vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                row.addWidget(vl, 1)
                grid.addLayout(row)
            lay.addLayout(grid)
            bits = QHBoxLayout()
            bits.addWidget(label(tr('水印位一致'), muted=True))
            bar = QFrame()
            bar.setFixedHeight(5)
            pct = h.bits / 63
            col = theme.T["ok"] if h.kind == "match" else theme.T["warn"]
            bar.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {col}, stop:{pct:.3f} {col}, "
                              f"stop:{min(1, pct + 0.001):.3f} {theme.T['line']}, stop:1 {theme.T['line']}); border-radius:2px;")
            bits.addWidget(bar, 1)
            bits.addWidget(label(f"{h.bits}/63", mono=True))
            lay.addLayout(bits)
        if h.note:
            lay.addWidget(label(h.note, muted=True, wrap=True))
        if r:
            b = QPushButton(tr('在簽發記錄中查看'))
            b.clicked.connect(lambda: self.show_record.emit(r.id))
            row = QHBoxLayout()
            row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)


class DocRow(QWidget):
    def __init__(self, d: Doc):
        super().__init__()
        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 7, 12, 7)
        hl.setSpacing(10)
        ic = QLabel(d.path.suffix.lstrip(".").upper()[:4])
        ic.setFixedSize(34, 42)
        ic.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        ic.setStyleSheet(f"border:1px solid {theme.T['line']}; border-top-right-radius:9px; background:{theme.T['surface2']};"
                         f"color:{theme.T['muted']}; font-size:9px; padding-bottom:4px;")
        col = QVBoxLayout()
        col.setSpacing(0)
        nm = QLabel(d.path.name)
        nm.setStyleSheet("font-weight:600;")
        self.meta = label("", muted=True)
        col.addWidget(nm)
        col.addWidget(self.meta)
        self.chip = Chip()
        hl.addWidget(ic)
        hl.addLayout(col, 1)
        hl.addWidget(self.chip)
        self.update_from(d)

    def update_from(self, d: Doc):
        if d.status == "wait":
            self.chip.set(tr('等待中'))
            self.meta.setText(d.path.suffix.lstrip(".").upper())
        elif d.status == "run":
            self.chip.set(tr('分析中'), "run")
            self.meta.setText(d.step + "…")
        else:
            r = d.result
            if r.error:
                self.chip.set(tr('無法讀取'), "bad")
                self.meta.setText(r.error)
            else:
                hits = r.hits
                n_wm = sum(1 for h in hits if h.kind != "none")
                self.meta.setText(tr('{v} 頁 · 找到 {v2} 個簽名，{n_wm} 個有水印', v=len(r.pages), v2=len(hits), n_wm=n_wm))
                if not hits:
                    self.chip.set(tr('未找到簽名'))
                elif any(h.kind == "weak" for h in hits) and not any(h.kind == "match" for h in hits):
                    self.chip.set(tr('需人工確認'), "warn")
                elif any(h.kind == "match" for h in hits):
                    self.chip.set(tr('已溯源'), "ok")
                else:
                    self.chip.set(tr('無匹配'), "bad")


class TracePage(QWidget):
    show_record = Signal(str)
    data_changed = Signal()

    def __init__(self, store: Store, get_password, toast):
        super().__init__()
        self.store, self.get_password, self.toast = store, get_password, toast
        self.docs: list[Doc] = []
        self.job = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)

        left = self.left = Panel(tr('待溯源文件'))
        drop = DropZone(tr('拖入文件、照片或掃描件'), tr('支持 PDF、Word（.docx）、JPG、PNG。照片和掃描件請盡量拍正、拍清楚'),
                        [(tr('選擇文件'), self.pick)])
        drop.dropped.connect(self.add_paths)
        left.bl.addWidget(drop)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left.bl.addWidget(self.list, 1)
        self.prog, self.prog_txt, rb = left.add_runbar()
        self.run_btn = QPushButton(tr('開始溯源'))
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self.run)
        rb.addWidget(self.run_btn)
        split.addWidget(left)

        right = self.right = Panel(tr('檢測結果'))
        body = QHBoxLayout()
        body.setSpacing(16)
        pv = QVBoxLayout()
        self.view = PageView()
        self.view.selected.connect(self._manual_region)
        pscroll = QScrollArea()
        pscroll.setWidgetResizable(True)
        pscroll.setWidget(self.view)
        pscroll.setMinimumWidth(260)
        pv.addWidget(pscroll, 1)
        pager = QHBoxLayout()
        self.prev_btn = QPushButton("‹")
        self.next_btn = QPushButton("›")
        for b in (self.prev_btn, self.next_btn):
            b.setFixedWidth(34)
        self.prev_btn.clicked.connect(lambda: self._turn(-1))
        self.next_btn.clicked.connect(lambda: self._turn(1))
        self.page_lbl = label("", muted=True, mono=True)
        pager.addWidget(self.prev_btn)
        pager.addStretch(1)
        pager.addWidget(self.page_lbl)
        pager.addStretch(1)
        pager.addWidget(self.next_btn)
        pv.addLayout(pager)
        self.manual_btn = QPushButton(tr('手動框選簽名'))
        self.manual_btn.setCheckable(True)
        self.manual_btn.toggled.connect(self._toggle_manual)
        pv.addWidget(self.manual_btn)
        body.addLayout(pv, 4)
        self.hits_box = QVBoxLayout()
        self.hits_box.setSpacing(10)
        hw = QWidget()
        hw.setLayout(self.hits_box)
        hscroll = QScrollArea()
        hscroll.setWidgetResizable(True)
        hscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hscroll.setWidget(hw)
        body.addWidget(hscroll, 6)
        right.bl.addLayout(body, 1)
        split.addWidget(right)
        left.setMinimumWidth(340)
        right.setMinimumWidth(560)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 7)
        self._show(-1)

    # ------------------------------------------------------------ input
    def pick(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr('選擇要溯源的文件'), str(Path.home()),
                                                tr('文件和圖片 (*.pdf *.docx *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)'))
        if files:
            self.add_paths([Path(f) for f in files])

    def add_paths(self, paths):
        added = 0
        for p in paths:
            p = Path(p)
            files = [q for q in p.rglob("*") if q.suffix.lower() in DOC_EXT] if p.is_dir() else [p]
            for f in files:
                if f.suffix.lower() not in DOC_EXT:
                    continue
                d = Doc(f)
                self.docs.append(d)
                row = DocRow(d)
                li = QListWidgetItem()
                li.setSizeHint(row.sizeHint())
                self.list.addItem(li)
                self.list.setItemWidget(li, row)
                added += 1
        if added:
            self.list.setCurrentRow(self.list.count() - 1)
            self.toast(tr('已加入 {added} 份文件', added=added))
        else:
            self.toast(tr('不支持這種文件，請用 PDF、Word 或圖片'))
        self.left.sub.setText(tr('{v} 份', v=len(self.docs)))

    # ------------------------------------------------------------ run
    def run(self):
        if self.job:
            return
        password = self.get_password()
        if len(password) < 12:
            self.toast(tr('請先在「設定」裏設定水印密碼'))
            return
        queue = [i for i, d in enumerate(self.docs) if d.status == "wait"]
        if not queue:
            self.toast(tr('所有文件都已分析'))
            return
        store = self.store

        def work(report, cancelled):
            for n, i in enumerate(queue):
                if cancelled():
                    break
                src = self.docs[i].path
                # keep a copy so the result can be checked again later
                target = store.kind_dir("docs") / src.name
                k = 2
                while target.exists():
                    target = store.kind_dir("docs") / f"{src.stem}-{k}{src.suffix}"
                    k += 1
                try:
                    shutil.copy2(src, target)
                    store.track(target, "docs")
                except OSError:
                    target = src
                report(("run", i, n, len(queue), tr('讀取頁面')))
                res = trace.analyze(store, password, target, lambda s, i=i, n=n: report(("run", i, n, len(queue), s)))
                res.path = target
                report(("done", i, n + 1, len(queue), res))

        self.run_btn.setEnabled(False)
        self.prog.setValue(0)
        self.job = start_job(work, self._progress, self._done, self._failed)

    def _progress(self, msg):
        kind, i, n, total, payload = msg
        d = self.docs[i]
        if kind == "run":
            d.status, d.step = "run", payload
            self.prog_txt.setText(tr('正在分析 {name}（{v}/{total}）：{payload}', name=d.path.name, v=n + 1, total=total, payload=payload))
            if self.list.currentRow() != i:
                self.list.setCurrentRow(i)
        else:
            d.status, d.result = "done", payload
            d.page = payload.hits[0].page if payload.hits else 1
            self.prog.setValue(int(n / total * 100))
            self.data_changed.emit()
        self.list.itemWidget(self.list.item(i)).update_from(d)
        if self.list.currentRow() == i:
            self._show(i)

    def _done(self, _r):
        self.job = None
        self.run_btn.setEnabled(True)
        matched = sum(1 for d in self.docs if d.result and any(h.kind == "match" for h in d.result.hits))
        self.prog_txt.setText(tr('完成：{matched} 份文件找到了對應記錄', matched=matched))

    def _failed(self, err):
        self.job = None
        self.run_btn.setEnabled(True)
        self.prog_txt.setText(tr('出錯：{err}', err=err))

    # ------------------------------------------------------------ detail
    def _clear_hits(self):
        while self.hits_box.count():
            w = self.hits_box.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _empty(self, text):
        lb = QLabel(text)
        lb.setObjectName("empty")
        lb.setWordWrap(True)
        lb.setAlignment(Qt.AlignCenter)
        lb.setMinimumHeight(80)
        self.hits_box.addWidget(lb)
        self.hits_box.addStretch(1)

    def _show(self, i):
        self._clear_hits()
        d = self.docs[i] if 0 <= i < len(self.docs) else None
        self.right.sub.setText(d.path.name if d else "")
        can_page = bool(d and d.result and d.result.pages)
        for b in (self.prev_btn, self.next_btn, self.manual_btn):
            b.setEnabled(can_page)
        if not d:
            self.view.set_page(None, [])
            self.page_lbl.setText("")
            self._empty(tr('把文件拖到左邊，然後點「開始溯源」。'))
            return
        if not d.result:
            self.view.set_page(None, [])
            self.page_lbl.setText("")
            self._empty(tr('正在分析：') + d.step if d.status == "run" else tr('這份文件還沒分析。點左下角「開始溯源」。'))
            return
        r = d.result
        if r.error:
            self.view.set_page(None, [])
            self._empty(r.error)
            return
        page = r.pages[d.page - 1] if r.pages else None
        numbered = [(n + 1, h) for n, h in enumerate(r.hits)]
        self.view.set_page(pil_to_pixmap(page.preview) if page else None, [(n, h) for n, h in numbered if h.page == d.page])
        self.page_lbl.setText(f"{d.page} / {len(r.pages)}")
        self.prev_btn.setEnabled(d.page > 1)
        self.next_btn.setEnabled(d.page < len(r.pages))
        if not r.hits:
            self._empty(tr('這份文件裏沒有找到簽名。\n如果簽名很小或被印章蓋住，點「手動框選簽名」後在頁面上拖出一個框。'))
            return
        for n, h in numbered:
            card = HitCard(n, h)
            card.show_record.connect(self.show_record.emit)
            self.hits_box.addWidget(card)
        self.hits_box.addStretch(1)

    def _turn(self, step):
        d = self.docs[self.list.currentRow()]
        if d.result and d.result.pages:
            d.page = max(1, min(len(d.result.pages), d.page + step))
            self._show(self.list.currentRow())

    def _toggle_manual(self, on):
        self.view.manual = on
        self.view.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)
        if on:
            self.toast(tr('在頁面上拖出一個框，把簽名框進去'))

    def _manual_region(self, box):
        i = self.list.currentRow()
        d = self.docs[i]
        password = self.get_password()
        self.manual_btn.setChecked(False)
        res, pno = d.result, d.page

        def work(_report, _cancelled):
            img, k = trace.full_page(res, pno)
            full_box = tuple(int(v * k) for v in box)
            hit = trace.analyze_image_region(self.store, password, img, pno, full_box)
            hit.box = box
            return hit

        def done(hit):
            if hit.kind == "none":
                hit.note = tr('框選的區域裏沒有找到本工具的水印。可以把框拉大一點，包含簽名周圍的空白再試。')
            res.hits.append(hit)
            self.list.itemWidget(self.list.item(i)).update_from(d)
            self._show(i)

        self.toast(tr('正在分析框選的區域…'))
        start_job(work, None, done, lambda e: self.toast(tr('分析失敗：{e}', e=e)))
