"""Colours and stylesheet, taken from the HTML prototype's tokens."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

LIGHT = {
    "desk": "#E9EDF3", "surface": "#FFFFFF", "surface2": "#F3F5F9", "line": "#D6DCE6",
    "ink": "#18213A", "muted": "#5E6982", "accent": "#2B49B5", "accent_ink": "#FFFFFF", "accent_soft": "#E4EAFB",
    "ok": "#1E7A4C", "ok_soft": "#DFF2E7", "warn": "#9A5B00", "warn_soft": "#FAEED6",
    "bad": "#B3261E", "bad_soft": "#FBE3E1", "chrome": "#DFE4EC",
    "c1": "#2B49B5", "c2": "#23837F", "c3": "#B07A1E", "c4": "#8A93A6",
}
DARK = {
    "desk": "#0D1118", "surface": "#161B25", "surface2": "#1C2230", "line": "#2A3242",
    "ink": "#E5E9F2", "muted": "#96A0B5", "accent": "#829DFF", "accent_ink": "#0D1118", "accent_soft": "#212C4C",
    "ok": "#5FCB92", "ok_soft": "#15301F", "warn": "#E4AA4E", "warn_soft": "#33270F",
    "bad": "#F2847B", "bad_soft": "#3A1A18", "chrome": "#1A202B",
    "c1": "#829DFF", "c2": "#5BC2BC", "c3": "#E0B058", "c4": "#6F7A90",
}

MONO = '"IBM Plex Mono"'
BASE = {"px": 13}

T = dict(LIGHT)


def is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return QGuiApplication.palette().color(QPalette.Window).lightness() < 128


def apply(app, lang: str = "zh_Hant") -> None:
    from . import fonts
    fonts.load_bundled()
    app.setFont(fonts.app_font(lang))
    BASE["px"] = fonts.ui_pixel_size(lang)
    app.setLayoutDirection(Qt.RightToLeft if lang == "ar" else Qt.LeftToRight)
    T.clear()
    T.update(DARK if is_dark() else LIGHT)
    pal = QPalette()
    for role, key in ((QPalette.Window, "surface"), (QPalette.Base, "surface"), (QPalette.AlternateBase, "surface2"),
                      (QPalette.Text, "ink"), (QPalette.WindowText, "ink"), (QPalette.Button, "surface"),
                      (QPalette.ButtonText, "ink"), (QPalette.Highlight, "accent"), (QPalette.HighlightedText, "accent_ink"),
                      (QPalette.PlaceholderText, "muted"), (QPalette.ToolTipBase, "ink"), (QPalette.ToolTipText, "surface")):
        pal.setColor(role, QColor(T[key]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())


def stylesheet() -> str:
    t = T
    b = BASE["px"]
    return f"""
* {{ font-size: {b}px; color: {t['ink']}; }}
QMainWindow, #central {{ background: {t['surface']}; }}
#side {{ background: {t['surface2']}; border-right: 1px solid {t['line']}; }}
#side QPushButton {{ text-align: left; border: 0; padding: 9px 12px; border-radius: 7px; color: {t['muted']}; font-size: {b + 1}px; background: transparent; }}
#side QPushButton:hover {{ background: {t['surface']}; color: {t['ink']}; }}
#side QPushButton:checked {{ background: {t['surface']}; color: {t['accent']}; font-weight: 600; border: 1px solid {t['line']}; }}
#sideGroup {{ color: {t['muted']}; font-size: {b - 2}px; padding: 10px 12px 2px; }}
#pageTitle {{ font-size: {b + 5}px; font-weight: 700; }}
#pageSub, .muted, QLabel[muted="true"] {{ color: {t['muted']}; }}
QLabel[muted="true"] {{ font-size: {b - 1}px; }}
QLabel[mono="true"] {{ font-family: {MONO}; }}
#panel {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: 8px; }}
#panelHead {{ border-bottom: 1px solid {t['line']}; }}
#panelHead QLabel#panelTitle {{ font-weight: 600; }}
#runbar {{ background: {t['surface2']}; border-top: 1px solid {t['line']}; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; }}
#drop {{ background: {t['surface2']}; border: 1.5px dashed {t['line']}; border-radius: 8px; }}
#drop[over="true"] {{ background: {t['accent_soft']}; border-color: {t['accent']}; }}
QPushButton {{ border: 1px solid {t['line']}; background: {t['surface']}; padding: 6px 14px; border-radius: 7px; }}
QPushButton:hover {{ border-color: {t['muted']}; }}
QPushButton:disabled {{ color: {t['muted']}; }}
QPushButton#primary {{ background: {t['accent']}; border-color: {t['accent']}; color: {t['accent_ink']}; font-weight: 600; padding: 8px 20px; }}
QPushButton#primary:disabled {{ background: {t['line']}; border-color: {t['line']}; }}
QPushButton#danger {{ background: {t['bad']}; border-color: {t['bad']}; color: {t['surface']}; font-weight: 600; padding: 8px 20px; }}
QPushButton#danger:disabled {{ background: {t['line']}; border-color: {t['line']}; color: {t['muted']}; }}
QPushButton#seg {{ border: 0; padding: 4px 10px; border-radius: 6px; color: {t['muted']}; background: transparent; font-size: {b - 1}px; }}
QPushButton#seg:checked {{ background: {t['accent_soft']}; color: {t['accent']}; font-weight: 600; }}
#segBox {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: 8px; }}
QLineEdit, QComboBox, QSpinBox {{ border: 1px solid {t['line']}; border-radius: 6px; padding: 6px 8px; background: {t['surface']}; selection-background-color: {t['accent']}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {t['accent']}; }}
QLineEdit[readOnly="true"] {{ background: {t['surface2']}; font-family: {MONO}; font-size: {b - 1}px; }}
QListWidget, QTableView {{ border: 0; background: {t['surface']}; outline: 0; }}
QListWidget::item {{ border-bottom: 1px solid {t['line']}; }}
QListWidget::item:selected {{ background: {t['accent_soft']}; }}
QHeaderView::section {{ background: {t['surface2']}; color: {t['muted']}; border: 0; border-bottom: 1px solid {t['line']}; padding: 7px 10px; font-size: {b - 1}px; }}
QTableView {{ gridline-color: {t['line']}; selection-background-color: {t['accent_soft']}; selection-color: {t['ink']}; }}
QTableView::item {{ padding: 6px 10px; border-bottom: 1px solid {t['line']}; }}
QProgressBar {{ border: 0; background: {t['line']}; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 3px; }}
QSlider::groove:horizontal {{ height: 4px; background: {t['line']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t['surface']}; border: 2px solid {t['accent']}; width: 12px; height: 12px; margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:disabled {{ border-color: {t['line']}; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
#check {{ border: 1px solid {t['line']}; border-radius: 7px; background: {t['surface']}; }}
#check[on="true"] {{ border-color: {t['accent']}; background: {t['accent_soft']}; }}
#modeCard {{ border: 1px solid {t['line']}; border-radius: 7px; background: {t['surface']}; }}
#modeCard[on="true"] {{ border: 2px solid {t['accent']}; }}
#hitCard {{ border: 1px solid {t['line']}; border-radius: 7px; background: {t['surface']}; }}
#notice {{ border: 1px solid {t['accent']}; background: {t['accent_soft']}; border-radius: 8px; }}
#confirm {{ border: 1px solid {t['bad']}; background: {t['bad_soft']}; border-radius: 8px; }}
#empty {{ border: 1px dashed {t['line']}; border-radius: 7px; color: {t['muted']}; }}
QStatusBar {{ background: {t['chrome']}; border-top: 1px solid {t['line']}; }}
QStatusBar QLabel {{ color: {t['muted']}; font-size: {b - 1}px; padding: 0 8px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QToolTip {{ background: {t['ink']}; color: {t['surface']}; border: 0; padding: 6px 8px; }}
"""


def chip_style(kind: str) -> str:
    bg, fg = {
        "ok": ("ok_soft", "ok"), "warn": ("warn_soft", "warn"), "bad": ("bad_soft", "bad"),
        "run": ("accent_soft", "accent"),
    }.get(kind, ("surface2", "muted"))
    return f"background:{T[bg]}; color:{T[fg]}; border-radius:9px; padding:2px 8px; font-size:{BASE['px'] - 2}px;"
