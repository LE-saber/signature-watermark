"""備份與恢復, 清理空間 pages."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QRadioButton, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from .. import backup
from ..storage import Store
from . import theme
from .widgets import Chip, CheckRow, Panel, PathPicker, fmt_bytes, label, start_job
from ..i18n import tr

KIND_LABEL = {"uploads": tr('曾上傳的原始圖片'), "outputs": tr('加工後的水印圖片'), "docs": tr('溯源時導入的文件'), "cache": tr('臨時文件與預覽快取')}
KIND_COLOR = {"uploads": "c1", "outputs": "c2", "docs": "c3", "cache": "c4"}


def _scroll(widget: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setWidget(widget)
    return s


class BackupPage(QWidget):
    data_changed = Signal()

    def __init__(self, store: Store, toast):
        super().__init__()
        self.store, self.toast = store, toast
        self.job = None
        self.manifest = None
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(20)

        # create
        mk = self.mk = Panel(tr('建立備份'))
        mk.bl.addWidget(label(tr('要包含的內容'), muted=True))
        self.rows: dict[str, CheckRow] = {}
        for part, title, sub, on in (
                ("settings", tr('設定'), tr('載體參數、預設值、輸出規則（水印密碼另外勾選）'), True),
                ("records", tr('簽發記錄'), tr('溯源必需'), True),
                ("uploads", tr('曾上傳的原始圖片'), "", True),
                ("outputs", tr('加工後的水印圖片'), "", True),
                ("docs", tr('溯源時導入的文件'), "", False)):
            row = CheckRow(title, sub, on)
            row.toggled.connect(lambda _v: self._summary())
            self.rows[part] = row
            mk.bl.addWidget(row)
        self.enc = QCheckBox(tr('用密碼加密備份文件'))
        self.enc.setChecked(True)
        self.enc.toggled.connect(self._sync_enc)
        mk.bl.addWidget(self.enc)
        self.bk_pw_lbl = label(tr('備份密碼（恢復時需要，和水印密碼分開，至少 8 個字元）'), muted=True)
        self.bk_pw = QLineEdit()
        self.bk_pw.setEchoMode(QLineEdit.Password)
        mk.bl.addWidget(self.bk_pw_lbl)
        mk.bl.addWidget(self.bk_pw)
        self.inc_pw = QCheckBox(tr('同時備份水印密碼（換電腦時可直接恢復）'))
        mk.bl.addWidget(self.inc_pw)
        mk.bl.addWidget(label(tr('保存到'), muted=True))
        self.dest = PathPicker(tr('選擇備份保存位置'))
        self.dest.set_path(str(store.backup_dir))
        self.dest.changed.connect(self._set_dest)
        mk.bl.addWidget(self.dest)
        mk.bl.addStretch(1)
        self.prog, self.prog_txt, rb = mk.add_runbar()
        self.mk_btn = QPushButton(tr('建立備份'))
        self.mk_btn.setObjectName("primary")
        self.mk_btn.clicked.connect(self.create)
        rb.addWidget(self.mk_btn)
        root.addWidget(mk, 1)

        # restore + history
        col = QVBoxLayout()
        col.setSpacing(20)
        rs = Panel(tr('從備份恢復'))
        rs.bl.addWidget(label(tr('備份文件'), muted=True))
        self.rs_file = PathPicker(tr('選擇備份文件'), folder=False, filter_=tr('SigWatermark 備份 (*.swbak)'))
        self.rs_file.changed.connect(self._pick_restore)
        rs.bl.addWidget(self.rs_file)
        self.rs_pw_lbl = label(tr('備份密碼'), muted=True)
        self.rs_pw = QLineEdit()
        self.rs_pw.setEchoMode(QLineEdit.Password)
        self.rs_pw.returnPressed.connect(self._read_manifest)
        self.rs_read = QPushButton(tr('讀取備份內容'))
        self.rs_read.clicked.connect(self._read_manifest)
        for w in (self.rs_pw_lbl, self.rs_pw, self.rs_read):
            rs.bl.addWidget(w)
        self.rs_parts_box = QVBoxLayout()
        self.rs_parts_box.setSpacing(8)
        rs.bl.addLayout(self.rs_parts_box)
        modes = QHBoxLayout()
        self.rs_merge = QRadioButton(tr('合併：保留現有內容，相同 ID 的記錄跳過'))
        self.rs_over = QRadioButton(tr('覆蓋：先清空所選部分再替換'))
        self.rs_merge.setChecked(True)
        mv = QVBoxLayout()
        mv.addWidget(self.rs_merge)
        mv.addWidget(self.rs_over)
        modes.addLayout(mv)
        rs.bl.addLayout(modes)
        self.rs_hint = label("", muted=True, wrap=True)
        rs.bl.addWidget(self.rs_hint)
        rrow = QHBoxLayout()
        self.rs_btn = QPushButton(tr('恢復所選內容'))
        self.rs_btn.setObjectName("primary")
        self.rs_btn.clicked.connect(self.restore)
        rrow.addWidget(self.rs_btn)
        rrow.addStretch(1)
        rs.bl.addLayout(rrow)
        col.addWidget(rs)
        hist = self.hist_panel = Panel(tr('備份歷史'))
        hist.bl.setContentsMargins(0, 0, 0, 0)
        self.hist = QListWidget()
        self.hist.setMinimumHeight(140)
        hist.bl.addWidget(self.hist)
        col.addWidget(hist, 1)
        wrap = QWidget()
        wrap.setLayout(col)
        root.addWidget(_scroll(wrap), 1)
        self._sync_enc(True)
        self._restore_state(None)
        self.refresh()

    # ------------------------------------------------------------ create
    def refresh(self):
        u = self.store.usage()
        for part, row in self.rows.items():
            if part in ("uploads", "outputs", "docs"):
                files = backup._files_for(self.store, part)
                size = sum(p.stat().st_size for p, _ in files)
                row.size.setText(fmt_bytes(size))
                row.s.setText(tr('{v} 個文件', v=len(files)))
                unb = u[part]["count"] - u[part]["backed_count"]
                row.chip.set(tr('{unb} 項未備份', unb=unb) if unb > 0 else "", "warn")
            elif part == "records":
                row.size.setText(fmt_bytes(u["records"]["bytes"]))
                row.s.setText(tr('{v} 條，溯源必需', v=u['records']['count']))
            else:
                row.size.setText("< 1 KB")
        last = self.store.last_backup()
        self.mk.sub.setText(tr('上次備份 {v}', v=last.replace('T', ' ')[:16]) if last else tr('還沒有備份過'))
        self._summary()
        self._history()

    def _summary(self):
        parts = [p for p, r in self.rows.items() if r.checked()]
        if not parts:
            self.prog_txt.setText(tr('請至少選一項'))
            self.mk_btn.setEnabled(False)
            return
        self.mk_btn.setEnabled(self.job is None)
        self.prog_txt.setText(tr('已選 {v} 項，預計約 {v2}', v=len(parts), v2=fmt_bytes(backup.estimate(self.store, parts))))

    def _sync_enc(self, on):
        for w in (self.bk_pw_lbl, self.bk_pw):
            w.setVisible(on)
        self.inc_pw.setEnabled(on)
        if not on:
            self.inc_pw.setChecked(False)

    def _set_dest(self, p):
        self.store.settings.backup_dir = p
        self.store.save_settings()

    def create(self):
        parts = [p for p, r in self.rows.items() if r.checked()]
        pw = self.bk_pw.text() if self.enc.isChecked() else ""
        if self.enc.isChecked() and len(pw) < 8:
            self.toast(tr('備份密碼至少 8 個字元'))
            return
        dest = Path(self.dest.path())
        inc = self.inc_pw.isChecked()

        def work(report, _c):
            return backup.create(self.store, dest, parts, pw, inc, lambda i, n, name: report((i, n, name)))

        def prog(m):
            i, n, name = m
            self.prog.setValue(int(i / max(1, n) * 100))
            self.prog_txt.setText(tr('正在打包 {name}（{i}/{n}）', name=name, i=i, n=n) if name else tr('正在寫入…'))

        def done(path):
            self.job = None
            self.prog.setValue(100)
            self.refresh()
            self.prog_txt.setText(tr('已保存到 {path}', path=path))
            self.toast(tr('備份完成'))
            self.data_changed.emit()

        def failed(err):
            self.job = None
            self._summary()
            self.prog_txt.setText(tr('備份失敗：{err}', err=err))

        self.mk_btn.setEnabled(False)
        self.job = start_job(work, prog, done, failed)

    def _history(self):
        self.hist.clear()
        items = self.store.backups()
        self.hist_panel.sub.setText(tr('{v} 份', v=len(items)))
        for b in items:
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(12, 8, 12, 8)
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(label(Path(b["path"]).name, mono=True))
            parts = tr('、').join(backup.PART_LABELS[p] for p in b["parts"])
            sub = f"{b['created'].replace('T', ' ')[:16]} · {fmt_bytes(b['size'])} · {parts}" + (tr(' · 已加密') if b["encrypted"] else "")
            if not b["exists"]:
                sub += tr(' · 文件已不在原位置')
            col.addWidget(label(sub, muted=True, wrap=True))
            hl.addLayout(col, 1)
            if b["exists"]:
                ob = QPushButton(tr('所在資料夾'))
                ob.clicked.connect(lambda _=False, p=b["path"]: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(p).parent))))
                rb = QPushButton(tr('恢復'))
                rb.clicked.connect(lambda _=False, p=b["path"]: (self.rs_file.set_path(p), self._pick_restore(p)))
                hl.addWidget(ob)
                hl.addWidget(rb)
            li = QListWidgetItem()
            li.setSizeHint(w.sizeHint())
            self.hist.addItem(li)
            self.hist.setItemWidget(li, w)

    # ------------------------------------------------------------ restore
    def _restore_state(self, manifest):
        self.manifest = manifest
        while self.rs_parts_box.count():
            w = self.rs_parts_box.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.rs_part_rows = {}
        has = manifest is not None
        for w in (self.rs_merge, self.rs_over, self.rs_btn):
            w.setVisible(has)
        if has:
            self.rs_parts_box.addWidget(label(tr('這份備份建立於 {v}，包含：', v=manifest['created'].replace('T', ' ')[:16]), muted=True))
            counts: dict[str, int] = {}
            for info in manifest["files"].values():
                counts[info["part"]] = counts.get(info["part"], 0) + 1
            for p in manifest["parts"]:
                row = CheckRow(backup.PART_LABELS[p], tr('{v} 個文件', v=counts[p]) if p in counts else "", True)
                self.rs_part_rows[p] = row
                self.rs_parts_box.addWidget(row)
            if manifest.get("has_secret"):
                self.rs_parts_box.addWidget(label(tr('另含水印密碼，恢復「設定」時會一併寫入系統鑰匙串。'), muted=True, wrap=True))

    def _pick_restore(self, path):
        self.rs_hint.setText("")
        self._restore_state(None)
        try:
            enc = backup.is_encrypted(Path(path))
        except Exception:  # noqa: BLE001
            self.rs_hint.setText(tr('這不是有效的 SigWatermark 備份文件'))
            enc = False
        for w in (self.rs_pw_lbl, self.rs_pw, self.rs_read):
            w.setVisible(enc)
        if not enc:
            self._read_manifest()

    def _read_manifest(self):
        path = self.rs_file.path()
        if not path:
            return
        try:
            m = backup.read_manifest(Path(path), self.rs_pw.text())
            self.rs_hint.setText("")
            self._restore_state(m)
        except backup.BackupError as exc:
            self.rs_hint.setText(str(exc))
            self._restore_state(None)

    def restore(self):
        parts = [p for p, r in self.rs_part_rows.items() if r.checked()]
        if not parts:
            self.rs_hint.setText(tr('請至少選一項'))
            return
        path, pw, over = Path(self.rs_file.path()), self.rs_pw.text(), self.rs_over.isChecked()

        def done(s):
            self.rs_btn.setEnabled(True)
            txt = tr('已恢復：{v}。新增 {v2} 條記錄', v=tr('、').join(backup.PART_LABELS[p] for p in parts), v2=s['records_added'])
            if s["records_skipped"]:
                txt += tr('，跳過 {v} 條重複記錄', v=s['records_skipped'])
            txt += tr('，恢復 {v} 個文件', v=s['files']) + (tr('，水印密碼已寫入') if s["password"] else "") + tr('。')
            self.rs_hint.setText(txt)
            self.toast(tr('恢復完成'))
            self.refresh()
            self.data_changed.emit()

        def failed(err):
            self.rs_btn.setEnabled(True)
            self.rs_hint.setText(tr('恢復失敗：{err}', err=err))

        self.rs_btn.setEnabled(False)
        self.rs_hint.setText(tr('正在恢復…'))
        start_job(lambda _r, _c: backup.restore(self.store, path, parts, pw, over), None, done, failed)


class UsageBar(QWidget):
    def __init__(self):
        super().__init__()
        self.parts: list[tuple[float, str]] = []
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_parts(self, parts):
        self.parts = parts
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        clip = QPainterPath()
        clip.addRoundedRect(r, 8, 8)
        p.setClipPath(clip)
        p.fillRect(r, QColor(theme.T["surface2"]))
        total = sum(v for v, _ in self.parts) or 1
        x = 0.0
        for v, col in self.parts:
            w = r.width() * v / total
            if w > 0:
                p.fillRect(QRectF(x, 0, w, self.height()), QColor(theme.T[col]))
                x += w
                p.fillRect(QRectF(x - 1, 0, 2, self.height()), QColor(theme.T["surface"]))


class CleanPage(QWidget):
    data_changed = Signal()
    go_backup = Signal()

    def __init__(self, store: Store, toast):
        super().__init__()
        self.store, self.toast = store, toast
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(20)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(inner))

        top = self.top = Panel(tr('資料目錄佔用'))
        self.nums = QHBoxLayout()
        self.nums.setSpacing(28)
        top.bl.addLayout(self.nums)
        self.bar = UsageBar()
        top.bl.addWidget(self.bar)
        self.legend = QHBoxLayout()
        self.legend.setSpacing(18)
        top.bl.addLayout(self.legend)
        root.addWidget(top)

        self.safe = QCheckBox(tr('只清理已備份的部分'))
        self.safe.setChecked(True)
        self.safe.toggled.connect(lambda _v: self.refresh())
        sel = Panel(tr('選擇要清理的內容'), self.safe)
        self.rows: dict[str, CheckRow] = {}
        for kind in ("uploads", "outputs", "docs", "cache"):
            row = CheckRow(KIND_LABEL[kind], "", kind in ("uploads", "cache"))
            row.toggled.connect(lambda _v: self._summary())
            self.rows[kind] = row
            sel.bl.addWidget(row)
        sel.bl.addWidget(label(tr('簽發記錄和設定不在清理範圍內，刪了就沒法溯源。保存在資料目錄以外的輸出圖片也不會被刪。'), muted=True, wrap=True))
        self.confirm = QFrame()
        self.confirm.setObjectName("confirm")
        cl = QHBoxLayout(self.confirm)
        cl.setContentsMargins(14, 10, 14, 10)
        self.confirm_txt = label("", wrap=True)
        cl.addWidget(self.confirm_txt, 1)
        cancel = QPushButton(tr('取消'))
        cancel.clicked.connect(lambda: self.confirm.hide())
        go = QPushButton(tr('確認刪除'))
        go.setObjectName("danger")
        go.clicked.connect(self._do_clean)
        cl.addWidget(cancel)
        cl.addWidget(go)
        self.confirm.hide()
        sel.bl.addWidget(self.confirm)
        _p, self.sum_txt, rb = sel.add_runbar()
        _p.hide()
        self.backup_first = QPushButton(tr('先去備份'))
        self.backup_first.clicked.connect(self.go_backup.emit)
        self.clean_btn = QPushButton(tr('清理所選'))
        self.clean_btn.setObjectName("danger")
        self.clean_btn.clicked.connect(self._ask)
        rb.addWidget(self.backup_first)
        rb.addWidget(self.clean_btn)
        root.addWidget(sel)
        root.addStretch(1)
        self.refresh()

    def _clear(self, lay):
        while lay.count():
            w = lay.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _free(self, kind) -> tuple[int, int]:
        u = self.usage[kind]
        if kind == "cache" or not self.safe.isChecked():
            return u["count"], u["bytes"]
        return u["backed_count"], u["backed_bytes"]

    def refresh(self):
        self.usage = u = self.store.usage()
        total = sum(u[k]["bytes"] for k in KIND_LABEL) + u["records"]["bytes"]
        self.top.sub.setText(str(self.store.root))
        self._clear(self.nums)
        unb = sum(u[k]["count"] - u[k]["backed_count"] for k in ("uploads", "outputs", "docs"))
        last = self.store.last_backup()
        for big, small in ((fmt_bytes(total), tr('總佔用')), (last.replace("T", " ")[5:16] if last else tr('從未'), tr('上次備份')),
                           (str(unb), tr('個文件還沒備份'))):
            box = QVBoxLayout()
            b = label(big, mono=True)
            b.setStyleSheet("font-size:22px; font-weight:700;")
            box.addWidget(b)
            box.addWidget(label(small, muted=True))
            w = QWidget()
            w.setLayout(box)
            self.nums.addWidget(w)
        self.nums.addStretch(1)
        self.bar.set_parts([(u[k]["bytes"], KIND_COLOR[k]) for k in KIND_LABEL] + [(u["records"]["bytes"], "line")])
        self._clear(self.legend)
        for k in KIND_LABEL:
            sw = QLabel()
            sw.setFixedSize(10, 10)
            sw.setStyleSheet(f"background:{theme.T[KIND_COLOR[k]]}; border-radius:3px;")
            self.legend.addWidget(sw)
            self.legend.addWidget(label(f"{KIND_LABEL[k]} {fmt_bytes(u[k]['bytes'])}", muted=True))
        self.legend.addWidget(label(tr('記錄與設定 {v}', v=fmt_bytes(u['records']['bytes'])), muted=True))
        self.legend.addStretch(1)
        for k, row in self.rows.items():
            n, b = self._free(k)
            row.s.setText(tr('共 {v} 項 · {v2}', v=u[k]['count'], v2=fmt_bytes(u[k]['bytes'])) + (tr(' · 沒有可清理的內容') if n == 0 else ""))
            row.size.setText(tr('可釋放 {v}', v=fmt_bytes(b)))
            unb_k = u[k]["count"] - u[k]["backed_count"]
            if k == "cache":
                row.chip.set(tr('無需備份'))
            elif unb_k > 0:
                row.chip.set(tr('{unb_k} 項未備份', unb_k=unb_k), "warn")
            else:
                row.chip.set(tr('已全部備份') if u[k]["count"] else "", "ok")
            row.set_enabled(n > 0)
        self.backup_first.setVisible(unb > 0)
        self._summary()

    def _selected(self):
        return [k for k, r in self.rows.items() if r.checked() and self._free(k)[0] > 0]

    def _summary(self):
        ks = self._selected()
        n = sum(self._free(k)[0] for k in ks)
        b = sum(self._free(k)[1] for k in ks)
        self.sum_txt.setText(tr('已選 {n} 個文件，可釋放 {v}', n=n, v=fmt_bytes(b)) if ks else tr('沒有選中可清理的內容'))
        self.clean_btn.setEnabled(bool(ks))
        self.confirm.hide()

    def _ask(self):
        ks = self._selected()
        n = sum(self._free(k)[0] for k in ks)
        b = sum(self._free(k)[1] for k in ks)
        risky = not self.safe.isChecked() and any(self.usage[k]["count"] > self.usage[k]["backed_count"] for k in ks if k != "cache")
        self.confirm_txt.setText(tr('將刪除 {n} 個文件，釋放 {v}。刪除後不能撤銷', n=n, v=fmt_bytes(b)) + (tr('，其中有還沒備份的文件。') if risky else tr('。')))
        self.confirm.show()

    def _do_clean(self):
        ks = self._selected()
        n, freed = self.store.delete_files(ks, only_backed_up=self.safe.isChecked())
        self.confirm.hide()
        self.refresh()
        self.toast(tr('已刪除 {n} 個文件，釋放 {v}', n=n, v=fmt_bytes(freed)))
        self.data_changed.emit()
