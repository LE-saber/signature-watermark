"""設定 page."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit,
                               QPushButton, QRadioButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import secret, service, storage
from ..storage import Store
from .page_embed import MODE_INFO
from .widgets import Panel, label
from .. import i18n
from ..i18n import tr


class SettingsPage(QWidget):
    password_changed = Signal()
    defaults_changed = Signal()
    records_changed = Signal()

    def __init__(self, store: Store, toast):
        super().__init__()
        self.store, self.toast = store, toast
        st = store.settings
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(16)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(sc)

        lg_panel = Panel(tr('界面語言'))
        lrow = QHBoxLayout()
        self.lang = QComboBox()
        self.lang.addItem(tr('跟隨系統'), "")
        for code, name in i18n.LANGUAGES.items():
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(st.language)))
        self.lang.currentIndexChanged.connect(self._language)
        lrow.addWidget(self.lang)
        self.restart_btn = QPushButton(tr('立即重新啟動'))
        self.restart_btn.clicked.connect(self._restart)
        self.restart_btn.hide()
        lrow.addWidget(self.restart_btn)
        lrow.addStretch(1)
        lg_panel.bl.addLayout(lrow)
        self.lang_hint = label("", muted=True, wrap=True)
        lg_panel.bl.addWidget(self.lang_hint)
        col.addWidget(lg_panel)

        # First run: offer a generated password instead of making the user invent one.
        self.first_run = QFrame()
        self.first_run.setObjectName("notice")
        fl = QVBoxLayout(self.first_run)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.addWidget(label(tr('還沒有水印密碼'), bold=True))
        fl.addWidget(label(tr('可以讓程式隨機生成一個高強度密碼並保存，也可以自己輸入至少 12 個字元的密碼。'), muted=True, wrap=True))
        frow = QHBoxLayout()
        gen_save = QPushButton(tr('隨機生成並保存（推薦）'))
        gen_save.setObjectName("primary")
        gen_save.clicked.connect(self._generate_and_save)
        own = QPushButton(tr('自己輸入'))
        own.clicked.connect(lambda: (self.first_run.hide(), self.pw.setFocus()))
        frow.addWidget(gen_save)
        frow.addWidget(own)
        frow.addStretch(1)
        fl.addLayout(frow)
        col.insertWidget(0, self.first_run)
        self.first_run.setVisible(len(secret.get_password(store)) < 12)

        pw = Panel(tr('水印密碼'))
        pw.bl.addWidget(label(tr('密碼決定了水印的打亂方式，提取和溯源時必須用同一個密碼。至少 12 個字元。換電腦時請用備份帶走，或記在安全的地方。'), muted=True, wrap=True))
        row = QHBoxLayout()
        self.pw = QLineEdit(secret.get_password(store))
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.textChanged.connect(self._check)
        show = QPushButton(tr('顯示'))
        show.setCheckable(True)
        show.toggled.connect(lambda on: (self.pw.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password), show.setText(tr('隱藏') if on else tr('顯示'))))
        row.addWidget(self.pw, 1)
        row.addWidget(show)
        pw.bl.addLayout(row)
        self.pw_hint = label("", muted=True, wrap=True)
        pw.bl.addWidget(self.pw_hint)
        brow = QHBoxLayout()
        save = QPushButton(tr('儲存密碼'))
        save.clicked.connect(self._save_pw)
        brow.addWidget(save)
        gen = QPushButton(tr('隨機生成'))
        gen.clicked.connect(self._generate)
        brow.addWidget(gen)
        copy = QPushButton(tr('複製'))
        copy.clicked.connect(self._copy)
        brow.addWidget(copy)
        self.show_btn = show
        legacy = secret.legacy_env_password(storage.program_dir())
        if legacy:
            imp = QPushButton(tr('使用舊版 .env 裏的密碼'))
            imp.clicked.connect(lambda: (self.pw.setText(legacy), self._save_pw()))
            brow.addWidget(imp)
        brow.addStretch(1)
        pw.bl.addLayout(brow)
        col.addWidget(pw)

        loc = Panel(tr('資料存放位置'))
        self.portable = QRadioButton(tr('便攜模式：記錄和輸出都放在程式旁邊的 data/ 資料夾，整個資料夾可以直接拷走'))
        self.user = QRadioButton(tr('使用者目錄：{v}（適合把程式放在唯讀位置）', v=storage.user_data_dir()))
        g = QButtonGroup(self)
        g.addButton(self.portable)
        g.addButton(self.user)
        (self.portable if store.portable else self.user).setChecked(True)
        self.portable.toggled.connect(self._storage_mode)
        loc.bl.addWidget(self.portable)
        loc.bl.addWidget(self.user)
        loc.bl.addWidget(label(tr('目前使用：{root}', root=store.root), muted=True, mono=True, wrap=True))
        col.addWidget(loc)

        d = Panel(tr('預設值'))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        grid.addWidget(label(tr('預設載體背景'), muted=True), 0, 0)
        self.mode = QComboBox()
        for k, name, _ in MODE_INFO:
            self.mode.addItem(name, k)
        self.mode.setCurrentIndex([k for k, *_ in MODE_INFO].index(st.mode) if st.mode in [k for k, *_ in MODE_INFO] else 3)
        grid.addWidget(self.mode, 1, 0)
        grid.addWidget(label(tr('備份提醒（天，0 = 不提醒）'), muted=True), 0, 1)
        self.remind = QSpinBox()
        self.remind.setRange(0, 365)
        self.remind.setValue(st.backup_reminder_days)
        grid.addWidget(self.remind, 1, 1)
        grid.addWidget(label(tr('輸出檔名規則（可用 {date} {short} {id} {src}）'), muted=True), 2, 0, 1, 2)
        self.naming = QLineEdit(st.naming)
        grid.addWidget(self.naming, 3, 0, 1, 2)
        d.bl.addLayout(grid)
        self.self_check = QCheckBox(tr('加水印後自動回提自檢（失敗的圖不輸出）'))
        self.self_check.setChecked(st.self_check)
        d.bl.addWidget(self.self_check)
        srow = QHBoxLayout()
        sv = QPushButton(tr('儲存預設值'))
        sv.clicked.connect(self._save_defaults)
        srow.addWidget(sv)
        srow.addStretch(1)
        d.bl.addLayout(srow)
        col.addWidget(d)

        lg = Panel(tr('舊版記錄'))
        lg.bl.addWidget(label(tr('如果用過舊版腳本（signature_watermark_blind.py），可以導入它在 out/watermark 裏留下的 SIG-*.txt 記錄，舊圖也能溯源。'), muted=True, wrap=True))
        lrow = QHBoxLayout()
        lb = QPushButton(tr('導入舊版記錄…'))
        lb.clicked.connect(self._import_legacy)
        lrow.addWidget(lb)
        lrow.addStretch(1)
        lg.bl.addLayout(lrow)
        col.addWidget(lg)
        col.addStretch(1)
        self._check()

    def _language(self, _i):
        self.store.settings.language = self.lang.currentData()
        self.store.save_settings()
        self.lang_hint.setText(tr('界面語言已更改，重新啟動程式後生效。'))
        self.restart_btn.show()

    def _restart(self):
        import sys
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        if QProcess.startDetached(sys.executable, args):
            QApplication.quit()
        else:
            self.toast(tr('無法自動重新啟動，請手動關閉後再打開'))

    def _generate(self):
        if secret.get_password(self.store) and self.store.record_count():
            self.pw_hint.setText(tr('注意：已有的簽發記錄是用舊密碼嵌入的，換密碼後這些圖片將無法提取。如果只是誤改，請改回原密碼。'))
        self.pw.setText(secret.generate_password())
        self.show_btn.setChecked(True)
        self.toast(tr('已生成隨機密碼，點「儲存密碼」後生效'))

    def _generate_and_save(self):
        self.pw.setText(secret.generate_password())
        self.show_btn.setChecked(True)
        self._save_pw()
        self.first_run.hide()
        self.pw_hint.setText(tr('密碼已隨機生成並保存。請在「備份與恢復」做一次加密備份並勾選「同時備份水印密碼」，或把密碼抄在安全的地方；丟了密碼就無法再溯源。'))

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        if self.pw.text():
            QApplication.clipboard().setText(self.pw.text())
            self.toast(tr('已複製到剪貼簿'))

    def _check(self):
        v = self.pw.text()
        if len(v) >= 12:
            where = tr('系統鑰匙串') if secret.keyring_available() else tr('資料目錄的 settings.json（這台電腦沒有可用的系統鑰匙串）')
            self.pw_hint.setText(tr('長度足夠。儲存後會存到{where}。', where=where))
            self.pw_hint.setStyleSheet("")
        else:
            self.pw_hint.setText(tr('還差 {v} 個字元', v=12 - len(v)))

    def _save_pw(self):
        v = self.pw.text()
        if len(v) < 12:
            self.toast(tr('密碼至少需要 12 個字元'))
            return
        old = secret.get_password(self.store)
        if old and old != v and self.store.record_count():
            self.pw_hint.setText(tr('注意：已有的簽發記錄是用舊密碼嵌入的，換密碼後這些圖片將無法提取。如果只是誤改，請改回原密碼。'))
        where = secret.set_password(self.store, v)
        self.first_run.hide()
        self.toast(tr('密碼已存入系統鑰匙串') if where == "keyring" else tr('密碼已存入資料目錄'))
        self.password_changed.emit()

    def _storage_mode(self, portable):
        storage.set_storage_mode(portable)
        self.toast(tr('下次啟動時生效。已有的資料不會自動搬移，可以用備份恢復帶過去'))

    def _save_defaults(self):
        st = self.store.settings
        st.mode = self.mode.currentData()
        st.backup_reminder_days = self.remind.value()
        st.naming = self.naming.text().strip() or "SIG-{date}-{short}"
        st.self_check = self.self_check.isChecked()
        self.store.save_settings()
        self.toast(tr('預設值已儲存'))
        self.defaults_changed.emit()

    def _import_legacy(self):
        d = QFileDialog.getExistingDirectory(self, tr('選擇舊版的 out 資料夾'), str(storage.program_dir()))
        if not d:
            return
        added, skipped = service.import_legacy(self.store, d)
        self.toast(tr('導入 {added} 條舊版記錄', added=added) + (tr('，跳過 {skipped} 條', skipped=skipped) if skipped else ""))
        if added:
            self.records_changed.emit()
