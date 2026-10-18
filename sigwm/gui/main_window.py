"""Main window: sidebar, pages, status bar, toast."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
                               QStatusBar, QVBoxLayout, QWidget)

from .. import __version__, secret
from ..storage import Store
from . import theme
from .page_data import BackupPage, CleanPage
from .page_embed import EmbedPage
from .page_records import RecordsPage
from .page_settings import SettingsPage
from .page_trace import TracePage
from .widgets import bold_width, fmt_bytes, label
from ..i18n import tr

PAGES = [
    ("embed", tr('批量加水印'), tr('每張圖會生成一個獨立 ID，並寫入簽發記錄。')),
    ("trace", tr('簽名溯源'), tr('上傳含電子簽名的文件、照片或掃描件，找出每個簽名出自哪一條簽發記錄。')),
    ("records", tr('簽發記錄'), tr('每次加水印都會在這裏留一條記錄。溯源時就是拿提取到的 ID 來這裏比對。')),
    ("backup", tr('備份與恢復'), tr('把設定、記錄和圖片打包成一個 .swbak 備份文件，可以只選需要的部分。')),
    ("clean", tr('清理空間'), tr('備份好以後，可以刪除不再需要的圖片和臨時文件。')),
    ("settings", tr('設定'), tr('密碼、資料位置和預設值。')),
]


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet(f"background:{theme.T['ink']}; color:{theme.T['surface']}; padding:9px 16px; border-radius:8px;")
        self.hide()
        self._t = QTimer(self, singleShot=True, interval=2600)
        self._t.timeout.connect(self.hide)

    def show_msg(self, text: str):
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 96)
        self.raise_()
        self.show()
        self._t.start()


class MainWindow(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.setWindowTitle("SigWatermark")
        self.resize(1240, 800)
        self.setMinimumSize(980, 640)
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        hl = QHBoxLayout(central)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        side = QFrame()
        side.setObjectName("side")
        self.side = side
        sl = QVBoxLayout(side)
        sl.setContentsMargins(10, 14, 10, 10)
        sl.setSpacing(4)
        self.nav = QButtonGroup(self)
        self.nav_btns = {}
        for i, (key, title, _sub) in enumerate(PAGES):
            if key == "backup":
                g = QLabel(tr('資料管理'))
                g.setObjectName("sideGroup")
                sl.addWidget(g)
            b = QPushButton(title)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.nav.addButton(b, i)
            self.nav_btns[key] = b
            sl.addWidget(b)
        sl.addStretch(1)
        # width follows the longest label in the current language
        widest = max(bold_width(b.text(), 1) for b in self.nav_btns.values())
        side.setFixedWidth(max(200, min(300, widest + 50)))
        self.key_lbl = label("", muted=True, wrap=True)
        sl.addWidget(self.key_lbl)
        hl.addWidget(side)

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(22, 18, 22, 18)
        ml.setSpacing(14)
        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.sub = QLabel()
        self.sub.setObjectName("pageSub")
        self.sub.setProperty("muted", True)
        head.addWidget(self.title)
        head.addSpacing(14)
        head.addWidget(self.sub, 1, Qt.AlignBottom)
        ml.addLayout(head)
        self.stack = QStackedWidget()
        ml.addWidget(self.stack, 1)
        hl.addWidget(main, 1)

        self.toast = Toast(central)
        t = self.toast.show_msg
        pw = lambda: secret.get_password(store)  # noqa: E731
        self.embed = EmbedPage(store, pw, t)
        self.trace = TracePage(store, pw, t)
        self.records = RecordsPage(store, t)
        self.backup = BackupPage(store, t)
        self.clean = CleanPage(store, t)
        self.settings = SettingsPage(store, t)
        for w in (self.embed, self.trace, self.records, self.backup, self.clean, self.settings):
            self.stack.addWidget(w)

        self.embed.records_changed.connect(self._data_changed)
        self.trace.data_changed.connect(self._data_changed)
        self.trace.show_record.connect(self._show_record)
        self.backup.data_changed.connect(self._data_changed)
        self.clean.data_changed.connect(self._data_changed)
        self.clean.go_backup.connect(lambda: self.go("backup"))
        self.settings.password_changed.connect(self._status)
        self.settings.defaults_changed.connect(self.embed.apply_defaults)
        self.settings.records_changed.connect(self._data_changed)
        self.nav.idClicked.connect(lambda i: self.go(PAGES[i][0]))

        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.sb_key = QLabel()
        self.sb_data = QLabel()
        self.sb_backup = QLabel()
        ver = QLabel(f"v{__version__}")
        for w in (self.sb_key, self.sb_data, self.sb_backup):
            sb.addWidget(w)
        sb.addPermanentWidget(ver)
        self.setStatusBar(sb)
        self._status()
        if len(pw()) < 12:
            self.go("settings")
            QTimer.singleShot(400, lambda: t(tr('歡迎使用。請先設定水印密碼（至少 12 個字元）')))
        else:
            self.go("embed")

    def go(self, key: str):
        i = [k for k, *_ in PAGES].index(key)
        self.nav_btns[key].setChecked(True)
        self.stack.setCurrentIndex(i)
        self.title.setText(PAGES[i][1])
        self.sub.setText(PAGES[i][2])
        if key == "backup":
            self.backup.refresh()
        elif key == "clean":
            self.clean.refresh()
        elif key == "records":
            self.records.refresh()

    def _show_record(self, rid: str):
        self.go("records")
        self.records.show_id(rid)

    def _data_changed(self):
        self.records.refresh()
        self._status()

    def _status(self):
        ok = len(secret.get_password(self.store)) >= 12
        dot = theme.T["ok" if ok else "bad"]
        txt = tr('密碼已設定') if ok else tr('尚未設定水印密碼')
        self.sb_key.setText(f"<span style='color:{dot}'>●</span> {txt}")
        self.key_lbl.setText(f"<span style='color:{dot}'>●</span> {txt}")
        u = self.store.usage()
        total = sum(u[k]["bytes"] for k in ("uploads", "outputs", "docs", "cache")) + u["records"]["bytes"]
        mode = tr('便攜') if self.store.portable else tr('使用者目錄')
        self.sb_data.setText(tr('資料目錄（{mode}）· {v} · {v2} 條記錄', mode=mode, v=fmt_bytes(total), v2=u['records']['count']))
        self.sb_data.setToolTip(str(self.store.root))
        last = self.store.last_backup()
        days = self.store.settings.backup_reminder_days
        unb = sum(u[k]["count"] - u[k]["backed_count"] for k in ("uploads", "outputs", "docs"))
        if last:
            age = (datetime.now().astimezone() - datetime.fromisoformat(last)).days
            msg = tr('上次備份 {v}', v=last.replace('T', ' ')[:16])
            if days and age >= days and unb:
                msg = tr("<span style='color:{v}'>已 {age} 天沒有備份，有 {unb} 個文件未備份</span>", v=theme.T['warn'], age=age, unb=unb)
        else:
            msg = tr("<span style='color:{v}'>還沒有備份過</span>", v=theme.T['warn']) if unb else tr('還沒有備份過')
        self.sb_backup.setText(msg)

    def closeEvent(self, e):
        for page in (self.embed, self.trace):
            if page.job:
                page.job.cancel()
        super().closeEvent(e)
