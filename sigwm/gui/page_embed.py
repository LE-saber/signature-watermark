"""批量加水印 page."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QSlider, QSplitter,
                               QVBoxLayout, QWidget, QScrollArea)

from .. import background, core, service
from ..storage import Store
from . import theme
from .widgets import Chip, DropZone, Panel, PathPicker, Segmented, label, pil_to_pixmap, start_job
from ..i18n import tr

MODE_INFO = [
    ("white", tr('白底'), tr('最穩，非白底文件上明顯')),
    ("translucent", tr('半透明'), tr('整塊均勻半透明')),
    ("feathered", tr('羽化'), tr('邊緣漸變到透明')),
    ("feathered_texture", tr('羽化 + 紋理'), tr('再加極淡噪聲紋理（推薦）')),
]
MODE_NAME = {k: n for k, n, _ in MODE_INFO}
PREVIEW_MAX = 900


@dataclass
class Item:
    path: Path
    status: str = "wait"          # wait | run | ok | warn | bad
    detail: str = ""
    out: str = ""
    size: tuple[int, int] = (0, 0)
    opaque: bool = False
    readable: bool = False
    preparation: tuple[bool, int] | None = None
    background_removed: bool = False
    thumb: Image.Image | None = None
    small: Image.Image | None = None  # downscaled RGBA for previews
    scale: float = 1.0
    error: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- preview scene

def _scene_bg(w: int, h: int, bg: str) -> Image.Image:
    s = w / 520
    img = Image.new("RGB", (w, h), "#ffffff")
    d = ImageDraw.Draw(img)
    if bg == "checker":
        q = max(4, int(10 * s))
        for y in range(0, h, q):
            for x in range(((y // q) % 2) * q, w, 2 * q):
                d.rectangle([x, y, x + q - 1, y + q - 1], fill="#e4e8ee")
        return img
    paper, bar, ink = {"white": ("#ffffff", "#d5dae3", "#8a93a3"), "cream": ("#f3e9d2", "#d6c7a6", "#8c7b58"),
                       "form": ("#e7ecf3", "#c3cddb", "#7d8899")}[bg]
    d.rectangle([0, 0, w, h], fill=paper)
    for i, k in enumerate((0.86, 0.92, 0.7, 0.88, 0.55)):
        y = (22 + i * 17) * s
        d.rectangle([28 * s, y, 28 * s + (w - 56 * s) * k, y + 6 * s], fill=bar)
    if bg == "form":
        d.rectangle([28 * s, 120 * s, w - 28 * s, 270 * s], outline=bar, width=max(1, int(1.5 * s)))
        d.rectangle([28 * s + 1, 120 * s + 1, 148 * s, 270 * s - 1], fill="#ffffff")
    d.line([w * 0.24, h * 0.5 + 58 * s, w * 0.78, h * 0.5 + 58 * s], fill=ink, width=max(1, int(1.2 * s)))
    return img


def render_scene(item: Item | None, p: core.CarrierParams, bg: str, show_carrier: bool, w: int, h: int) -> Image.Image:
    scene = _scene_bg(w, h, bg)
    if item is None or item.small is None:
        return scene
    sp = core.CarrierParams(p.mode, max(1, int(p.padding * item.scale)), p.alpha, max(1, int(p.feather * item.scale)), p.texture)
    try:
        master, _ = core.prepare_master(item.small, sp.padding)
    except core.WatermarkError:
        return scene
    layer = core.build_carrier(master, sp, 7) if show_carrier else master
    k = min(w * 0.78 / layer.width, h * 0.72 / layer.height)
    layer = layer.resize((max(1, int(layer.width * k)), max(1, int(layer.height * k))), Image.Resampling.LANCZOS)
    base = scene.convert("RGBA")
    base.alpha_composite(layer, ((w - layer.width) // 2, (h - layer.height) // 2))
    return base.convert("RGB")


def make_thumb(img: Image.Image, w: int = 152, h: int = 60) -> Image.Image:
    bg = _scene_bg(w, h, "checker").convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    if bbox:
        sig = img.crop(bbox)
        k = min((w - 8) / sig.width, (h - 6) / sig.height)
        sig = sig.resize((max(1, int(sig.width * k)), max(1, int(sig.height * k))), Image.Resampling.LANCZOS)
        bg.alpha_composite(sig, ((w - sig.width) // 2, (h - sig.height) // 2))
    return bg


def prepare_item(it: Item, p: core.CarrierParams, source: Image.Image | None = None) -> None:
    key = (p.remove_background, p.background_threshold)
    if not it.readable or it.preparation == key:
        return
    it.preparation = key
    it.small = it.thumb = None
    try:
        if source is None:
            source, _ = core.load_signature(it.path)
        img = core.prepare_signature(source, p)
        if img.getchannel("A").getbbox() is None:
            raise core.WatermarkError(tr('圖片沒有可見像素'))
        it.scale = min(1.0, PREVIEW_MAX / max(img.width, 1))
        it.small = img if it.scale == 1.0 else img.resize(
            (int(img.width * it.scale), max(1, int(img.height * it.scale))), Image.Resampling.LANCZOS)
        it.thumb = make_thumb(it.small)
        it.background_removed = it.opaque and p.remove_background
        it.error = ""
        if it.status == "bad":
            it.status = "wait"
    except core.WatermarkError as exc:
        it.error = str(exc)
        it.status = "bad"


def load_item(path: Path, params: core.CarrierParams | None = None) -> Item:
    it = Item(path)
    try:
        img, _ = core.load_signature(path)
        it.size = img.size
        it.opaque = background.has_paper_background(img)
        it.readable = True
        prepare_item(it, params or core.CarrierParams(), img)
    except core.WatermarkError as exc:
        it.error = str(exc)
    return it


# ---------------------------------------------------------------- list row

class FileRow(QWidget):
    remove = Signal()

    def __init__(self, item: Item):
        super().__init__()
        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 7, 12, 7)
        hl.setSpacing(10)
        self.thumb = QLabel()
        self.thumb.setFixedSize(76, 30)
        self.thumb.setScaledContents(True)
        if item.thumb:
            self.thumb.setPixmap(pil_to_pixmap(item.thumb))
        col = QVBoxLayout()
        col.setSpacing(0)
        self.name = QLabel(item.path.name)
        self.name.setStyleSheet("font-weight:600;")
        self.meta = label("", muted=True)
        col.addWidget(self.name)
        col.addWidget(self.meta)
        self.chip = Chip()
        x = QPushButton("✕")
        x.setFixedSize(26, 26)
        x.setStyleSheet("border:0; background:transparent;")
        x.setToolTip(tr('從列表移除'))
        x.clicked.connect(self.remove.emit)
        self.x = x
        hl.addWidget(self.thumb)
        hl.addLayout(col, 1)
        hl.addWidget(self.chip)
        hl.addWidget(x)
        self.update_from(item)

    def update_from(self, it: Item):
        if it.thumb:
            self.thumb.setPixmap(pil_to_pixmap(it.thumb))
        else:
            self.thumb.clear()
        labels = {"wait": (tr('等待中'), ""), "run": (tr('處理中'), "run"), "ok": (tr('完成'), "ok"),
                  "warn": (tr('完成，有提醒'), "warn"), "bad": (tr('失敗'), "bad")}
        self.chip.set(*labels[it.status])
        if it.status in ("ok", "warn"):
            meta = f"→ {it.out}" + (tr(' · {v}', v=tr('；').join(it.warnings)) if it.warnings else "")
        elif it.status == "bad":
            meta = it.error
        elif it.status == "run":
            meta = tr('提取筆跡、生成載體、嵌入 ID、回提自檢…')
        else:
            kind = tr('已去背景') if it.background_removed else (tr('非透明底') if it.opaque else tr('透明 PNG'))
            meta = tr('{v}×{v2} · {v3}', v=it.size[0], v2=it.size[1], v3=kind) if not it.error else it.error
        self.meta.setText(meta)
        self.meta.setToolTip(meta)


# ---------------------------------------------------------------- page

class EmbedPage(QWidget):
    records_changed = Signal()

    def __init__(self, store: Store, get_password, toast):
        super().__init__()
        self.store, self.get_password, self.toast = store, get_password, toast
        self.items: list[Item] = []
        self.job = None
        st = store.settings
        self.params = core.CarrierParams(st.mode, st.padding, st.alpha, st.feather, st.texture,
                                         st.remove_background, st.background_threshold)
        self.bg, self.show_carrier = "white", True
        self._timer = QTimer(self, singleShot=True, interval=90)
        self._timer.timeout.connect(self._render_preview)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)

        # left: files
        left = self.left = Panel(tr('待處理文件'))
        self.drop = DropZone(tr('把簽名圖或整個資料夾拖到這裏'), tr('支援白紙簽名照片、掃描圖和透明 PNG；預設自動去除紙張背景'),
                             [(tr('選擇文件'), self.pick_files), (tr('選擇資料夾'), self.pick_folder)])
        self.drop.dropped.connect(self.add_paths)
        left.bl.addWidget(self.drop)
        self.list = QListWidget()
        self.list.setMinimumHeight(220)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(lambda _r: self.schedule())
        left.bl.addWidget(self.list, 1)
        self.prog, self.prog_txt, rb = left.add_runbar()
        self.clear_btn = QPushButton(tr('清空列表'))
        self.clear_btn.clicked.connect(self.clear)
        self.run_btn = QPushButton(tr('開始加水印'))
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self.run)
        rb.addWidget(self.clear_btn)
        rb.addWidget(self.run_btn)
        split.addWidget(left)

        # right: preview + params
        right = self.right = Panel(tr('預覽與參數'))
        scroll = self.scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        rl = QVBoxLayout(inner)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)
        tools = QHBoxLayout()
        seg = Segmented([("white", tr('白色文件')), ("cream", tr('米黃紙')), ("form", tr('灰色表單')), ("checker", tr('透明'))], "white")
        seg.setToolTip(tr('僅切換預覽底色，輸出載體由下方樣式控制。'))
        seg.changed.connect(self._set_bg)
        tools.addWidget(seg)
        tools.addStretch(1)
        rl.addLayout(tools)
        tools = QHBoxLayout()
        self.carrier_cb = QCheckBox(tr('顯示載體'))
        self.carrier_cb.setChecked(True)
        self.carrier_cb.toggled.connect(self._set_carrier)
        tools.addWidget(self.carrier_cb)
        rl.addLayout(tools)
        self.background_cb = QCheckBox(tr('自動去除原圖背景'))
        self.background_cb.setChecked(self.params.remove_background)
        self.background_cb.toggled.connect(self._set_background_removal)
        rl.addWidget(self.background_cb)
        rl.addWidget(label(tr('先提取筆跡，再生成所選載體；透明 PNG 保留原樣。'), muted=True, wrap=True))
        self.preview = QLabel()
        self.preview.setMinimumSize(320, 180)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(f"border:1px solid {theme.T['line']}; border-radius:6px;")
        rl.addWidget(self.preview)
        self.capacity = label("", muted=True, wrap=True)
        rl.addWidget(self.capacity)

        rl.addWidget(label(tr('載體背景'), muted=True))
        grid = QGridLayout()
        grid.setSpacing(8)
        self.mode_cards = {}
        for i, (key, name, desc) in enumerate(MODE_INFO):
            card = QFrame()
            card.setObjectName("modeCard")
            card.setCursor(Qt.PointingHandCursor)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(6, 6, 6, 6)
            cl.setSpacing(3)
            img = QLabel()
            img.setFixedHeight(118)
            img.setAlignment(Qt.AlignCenter)
            t = QLabel(name)
            t.setStyleSheet("font-weight:600; font-size:12px;")
            dsc = label(desc, muted=True, wrap=True)
            dsc.setStyleSheet("font-size:11px;")
            cl.addWidget(img)
            cl.addWidget(t)
            cl.addWidget(dsc)
            card.mousePressEvent = lambda _e, k=key: self._set_mode(k)
            self.mode_cards[key] = (card, img)
            grid.addWidget(card, i // 2, i % 2)
        rl.addLayout(grid)

        sliders = QGridLayout()
        sliders.setHorizontalSpacing(18)
        sliders.setVerticalSpacing(6)
        self.sliders = {}
        for i, (key, text, lo, hi, unit) in enumerate((
                ("alpha", tr('透明度上限'), 12, 255, ""), ("feather", tr('邊緣羽化'), 4, 250, " px"),
                ("texture", tr('紋理強度'), 0, 20, ""), ("padding", tr('四周留白'), 16, 300, " px"),
                ("background_threshold", tr('筆跡保留閾值'), 100, 250, ""))):
            box = QVBoxLayout()
            box.setSpacing(2)
            head = QHBoxLayout()
            head.addWidget(label(text, muted=True))
            head.addStretch(1)
            val = label("", mono=True)
            head.addWidget(val)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(getattr(self.params, key))
            sl.valueChanged.connect(lambda v, k=key: self._set_param(k, v))
            if key == "background_threshold":
                sl.setToolTip(tr('提高可保留較淡筆跡，降低可去除陰影和雜點'))
            box.addLayout(head)
            box.addWidget(sl)
            self.sliders[key] = (sl, val, unit, text)
            sliders.addLayout(box, i // 2, i % 2)
        rl.addLayout(sliders)

        rl.addWidget(label(tr('用途（寫入記錄）'), muted=True))
        self.purpose = QLineEdit(st.purpose)
        rl.addWidget(self.purpose)
        rl.addWidget(label(tr('輸出位置'), muted=True))
        self.out = PathPicker(tr('選擇輸出資料夾'))
        self.out.set_path(str(store.output_dir))
        self.out.changed.connect(self._set_out)
        rl.addWidget(self.out)
        rl.addStretch(1)
        scroll.setWidget(inner)
        right.bl.addWidget(scroll)
        split.addWidget(right)
        left.setMinimumWidth(360)
        right.setMinimumWidth(500)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 6)
        self._sync_controls()
        self.schedule()

    # ------------------------------------------------------------ files
    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr('選擇簽名圖片'), str(Path.home()), tr('圖片 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)'))
        if files:
            self.add_paths([Path(f) for f in files])

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr('選擇包含簽名圖片的資料夾'), str(Path.home()))
        if d:
            self.add_paths([Path(d)])

    def add_paths(self, paths: list[Path]):
        if self.job:
            return
        files = service.expand_inputs(paths)
        known = {str(i.path.resolve()) for i in self.items}
        added = 0
        for f in files:
            if str(f.resolve()) in known:
                continue
            it = load_item(f, self.params)
            if it.error:
                it.status = "bad"
            self.items.append(it)
            self._add_row(it)
            added += 1
        if added:
            self.list.setCurrentRow(self.list.count() - 1)
        self.toast(tr('已加入 {added} 個文件', added=added) if added else tr('沒有新的圖片可加入'))
        self._summary()

    def _add_row(self, it: Item):
        row = FileRow(it)
        li = QListWidgetItem()
        li.setSizeHint(row.sizeHint())
        self.list.addItem(li)
        self.list.setItemWidget(li, row)
        row.remove.connect(lambda it=it: self._remove(it))

    def _remove(self, it: Item):
        if self.job:
            return
        i = self.items.index(it)
        self.items.pop(i)
        self.list.takeItem(i)
        self._summary()
        self.schedule()

    def clear(self):
        if self.job:
            return
        self.items.clear()
        self.list.clear()
        self._summary()
        self.schedule()

    def _row(self, i: int) -> FileRow:
        return self.list.itemWidget(self.list.item(i))

    def _summary(self):
        done = sum(1 for i in self.items if i.status in ("ok", "warn"))
        self.left.sub.setText(tr('{v} 張', v=len(self.items)) + (tr('，已完成 {done}', done=done) if done else ""))

    # ------------------------------------------------------------ params
    def _set_bg(self, bg):
        self.bg = bg
        self.schedule()

    def _set_carrier(self, on):
        self.show_carrier = on
        self.schedule()

    def _set_mode(self, mode):
        self.params.mode = mode
        self._invalidate_results()
        self._sync_controls()
        self.schedule()

    def _set_param(self, key, v):
        setattr(self.params, key, v)
        self._invalidate_results()
        if key == "background_threshold":
            self.store.settings.background_threshold = v
            self.store.save_settings()
        self._sync_controls()
        self.schedule()

    def _set_background_removal(self, enabled):
        self.params.remove_background = enabled
        self._invalidate_results()
        self.store.settings.remove_background = enabled
        self.store.save_settings()
        self._sync_controls()
        self.schedule()

    def _invalidate_results(self):
        for i, item in enumerate(self.items):
            if item.status in ("ok", "warn"):
                item.status, item.out, item.warnings = "wait", "", []
                self._row(i).update_from(item)
        self._summary()

    def _set_out(self, p):
        self.store.settings.output_dir = p
        self.store.save_settings()

    def _sync_controls(self):
        m = self.params.mode
        for key, (sl, val, unit, _t) in self.sliders.items():
            v = sl.value()
            enabled = not ((key == "alpha" and m == "white") or (key == "feather" and not m.startswith("feathered"))
                           or (key == "texture" and m != "feathered_texture")
                           or (key == "background_threshold" and (not self.params.remove_background or self.job)))
            sl.setEnabled(enabled)
            val.setText(("255" if key == "alpha" and m == "white" else ("±" if key == "texture" else "") + str(v)) + unit)
        for key, (card, _img) in self.mode_cards.items():
            card.setProperty("on", key == m)
            card.style().unpolish(card)
            card.style().polish(card)

    def apply_defaults(self):
        st = self.store.settings
        self.params = core.CarrierParams(st.mode, st.padding, st.alpha, st.feather, st.texture,
                                         st.remove_background, st.background_threshold)
        self.background_cb.blockSignals(True)
        self.background_cb.setChecked(st.remove_background)
        self.background_cb.blockSignals(False)
        for key, (sl, *_r) in self.sliders.items():
            sl.blockSignals(True)
            sl.setValue(getattr(self.params, key))
            sl.blockSignals(False)
        self._sync_controls()
        self.schedule()

    def schedule(self):
        self._timer.start()

    def current(self) -> Item | None:
        r = self.list.currentRow()
        return self.items[r] if 0 <= r < len(self.items) else None

    def _render_preview(self):
        it = self.current()
        if it:
            prepare_item(it, self.params)
            self._row(self.list.currentRow()).update_from(it)
        w = max(360, self.scroll.viewport().width() - 4)
        h = int(w * 300 / 520)
        self.preview.setFixedHeight(h)
        dpr = self.devicePixelRatioF()
        img = render_scene(it, self.params, self.bg, self.show_carrier, int(w * dpr), int(h * dpr))
        pm = pil_to_pixmap(img)
        pm.setDevicePixelRatio(dpr)
        self.preview.setPixmap(pm)
        demo = it if it and it.small is not None else None
        for key, (_card, lab) in self.mode_cards.items():
            p = core.CarrierParams(key, self.params.padding, self.params.alpha, self.params.feather, self.params.texture)
            tw = 200
            th = int(tw * 300 / 520)
            img = render_scene(demo, p, "cream" if self.bg == "checker" else self.bg, True, int(tw * dpr), int(th * dpr))
            pm = pil_to_pixmap(img)
            pm.setDevicePixelRatio(dpr)
            lab.setPixmap(pm)
        if it and it.small is not None and not it.error:
            bbox = it.small.getchannel("A").getbbox()
            sw = int((bbox[2] - bbox[0]) / it.scale)
            sh = int((bbox[3] - bbox[1]) / it.scale)
            W = max(sw + 2 * self.params.padding, core.MIN_CARRIER[0])
            H = max(sh + 2 * self.params.padding, core.MIN_CARRIER[1])
            cap = core.capacity_bits(W, H)
            self.capacity.setText(tr('輸出約 {W}×{H}   可嵌入 {cap} bit   水印 63 bit，重複約 {v} 次', W=W, H=H, cap=cap, v=cap // 63))
        elif it:
            self.capacity.setText(it.error or "")
        else:
            self.capacity.setText(tr('把簽名圖拖到左邊，這裏會顯示加上載體後的效果。'))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.schedule()

    # ------------------------------------------------------------ run
    def run(self):
        if self.job:
            self.job.cancel()
            self.run_btn.setEnabled(False)
            self.run_btn.setText(tr('正在停止…'))
            return
        password = self.get_password()
        if len(password) < 12:
            self.toast(tr('請先在「設定」裏設定或隨機生成水印密碼'))
            return
        queue = [i for i, it in enumerate(self.items) if it.status in ("wait", "bad") and it.readable]
        if not queue:
            self.toast(tr('沒有待處理的文件'))
            return
        self.params.validate()
        params = core.CarrierParams(**vars(self.params))
        purpose = self.purpose.text().strip() or "signature-use"
        self.store.settings.purpose = purpose
        self.store.save_settings()
        out_dir = Path(self.out.path()) if self.out.path() else None
        items = self.items

        def work(report, cancelled):
            for n, i in enumerate(queue):
                if cancelled():
                    return "stopped"
                report(("run", i, n, len(queue), None))
                res = service.embed_file(self.store, items[i].path, password, params, purpose, out_dir)
                report(("done", i, n + 1, len(queue), res))
            return "done"

        self.run_btn.setText(tr('停止'))
        self.right.setEnabled(False)
        self.background_cb.setEnabled(False)
        self.sliders["background_threshold"][0].setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.prog.setValue(0)
        self.job = start_job(work, self._on_progress, self._on_done, self._on_failed)

    def _on_progress(self, msg):
        kind, i, n, total, res = msg
        it = self.items[i]
        if kind == "run":
            it.status = "run"
            self.prog_txt.setText(tr('正在處理 {name}（{v}/{total}）', name=it.path.name, v=n + 1, total=total))
        else:
            if res.ok:
                it.status = "warn" if res.warnings else "ok"
                it.out, it.warnings = res.out_path.name, list(res.warnings)
                self.records_changed.emit()
            else:
                it.status, it.error = "bad", res.error
            self.prog.setValue(int(n / total * 100))
        self._row(i).update_from(it)
        self._summary()

    def _finish(self):
        self.job = None
        self.right.setEnabled(True)
        self.background_cb.setEnabled(True)
        self._sync_controls()
        self.run_btn.setEnabled(True)
        self.run_btn.setText(tr('開始加水印'))
        self.clear_btn.setEnabled(True)

    def _on_done(self, result):
        ok = sum(1 for i in self.items if i.status in ("ok", "warn"))
        bad = sum(1 for i in self.items if i.status == "bad")
        if result == "stopped":
            self.prog_txt.setText(tr('已停止'))
        else:
            self.prog_txt.setText(tr('完成：成功 {ok} 張', ok=ok) + (tr('，失敗 {bad} 張', bad=bad) if bad else "") + tr('，輸出到 {v}', v=self.out.path()))
            self.toast(tr('批量處理完成，記錄已更新'))
        self._finish()

    def _on_failed(self, err):
        self.prog_txt.setText(tr('出錯：{err}', err=err))
        self._finish()
