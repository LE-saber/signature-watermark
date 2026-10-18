"""簽發記錄 page."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QPushButton,
                               QTableView, QVBoxLayout, QWidget)

from ..storage import Store
from .page_embed import MODE_NAME
from .widgets import Panel
from ..i18n import tr

COLS = [tr('簽發 ID'), tr('用途'), tr('載體'), tr('尺寸'), tr('源文件'), tr('建立時間')]


class RecordsPage(QWidget):
    def __init__(self, store: Store, toast):
        super().__init__()
        self.store, self.toast = store, toast
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('搜尋 ID、用途或源文件'))
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self.refresh)
        bl.addWidget(self.search)
        bl.addStretch(1)
        for text, fn in ((tr('打開圖片'), self.open_image), (tr('打開輸出資料夾'), self.open_dir), (tr('匯出 CSV'), self.export)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bl.addWidget(b)
        panel = self.panel = Panel("", bar)
        self.model = QStandardItemModel(0, len(COLS))
        self.model.setHorizontalHeaderLabels(COLS)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda _i: self.open_image())
        panel.bl.setContentsMargins(0, 0, 0, 0)
        panel.bl.addWidget(self.table)
        root.addWidget(panel)
        self.refresh()

    def refresh(self, *_):
        self.records = self.store.records(self.search.text().strip())
        self.model.setRowCount(0)
        for r in self.records:
            row = [r.id, r.purpose, MODE_NAME.get(r.mode, r.mode or tr('舊版')), f"{r.width}×{r.height}", r.src_name,
                   r.created.replace("T", " ")[:16]]
            items = [QStandardItem(v) for v in row]
            items[0].setToolTip(r.out_path)
            self.model.appendRow(items)

    def show_id(self, rid: str):
        self.search.setText(rid)
        if self.records:
            self.table.selectRow(0)

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        return self.records[rows[0].row()] if rows else None

    def open_image(self):
        r = self._selected()
        if not r:
            self.toast(tr('先在表格裏選一條記錄'))
            return
        if not Path(r.out_path).exists():
            self.toast(tr('這張圖已被清理或移走；可以從備份恢復'))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(r.out_path))

    def open_dir(self):
        r = self._selected()
        folder = Path(r.out_path).parent if r and Path(r.out_path).exists() else self.store.output_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('匯出簽發記錄'), str(Path.home() / "SigWatermark-records.csv"), "CSV (*.csv)")
        if path:
            n = self.store.export_csv(Path(path))
            self.toast(tr('已匯出 {n} 條記錄', n=n))
