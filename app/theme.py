from __future__ import annotations

import sys
from typing import Literal

ThemeChoice = Literal["light", "dark", "system"]
ResolvedTheme = Literal["light", "dark"]

SHARED = """
* {
  font-family: "Candara", "Segoe UI Variable", "Segoe UI";
  font-size: 15px;
}

QMainWindow, QWidget#central {
  background: transparent;
}

QLabel#brand {
  font-family: "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: 48px;
  font-weight: 700;
  letter-spacing: -1px;
}

QLabel#sectionTitle {
  font-family: "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: 24px;
  font-weight: 700;
}

QLabel#tagline { font-size: 16px; font-weight: 500; }
QLabel#sectionHint { font-size: 14px; }
QLabel#meta { font-size: 16px; font-weight: 700; }
QLabel#metaSub { font-size: 14px; }
QLabel#muted { font-size: 14px; }
QLabel#state { font-size: 16px; font-weight: 800; }
QLabel#stateOk { font-size: 16px; font-weight: 800; }
QLabel#stateBad { font-size: 16px; font-weight: 800; }
QLabel#stateRun { font-size: 16px; font-weight: 800; }
QLabel#stateIdle { font-size: 15px; font-weight: 650; }
QLabel#jobLine { font-size: 14px; }
QLabel#jobUrl { font-size: 13px; font-weight: 600; }
QLabel#emptyTitle {
  font-family: "Palatino Linotype", Georgia, serif;
  font-size: 18px;
  font-weight: 700;
}

QFrame#panel { border-radius: 22px; }
QFrame#row { border-radius: 14px; }
QFrame#statusCard { border-radius: 18px; }
QFrame#dock { border: 0; border-radius: 24px; }

QLineEdit, QSpinBox, QComboBox {
  border-radius: 12px;
  padding: 11px 14px;
  min-height: 22px;
  font-size: 15px;
}
QComboBox::drop-down { border: 0; width: 28px; }
QSpinBox::up-button, QSpinBox::down-button { width: 18px; }

QPushButton {
  border-radius: 12px;
  padding: 11px 16px;
  font-size: 15px;
  font-weight: 650;
}
QPushButton#danger {
  min-width: 38px;
  max-width: 44px;
  padding: 8px 0;
  font-size: 18px;
}
QPushButton#start {
  min-width: 180px;
  min-height: 52px;
  border: 0;
  border-radius: 16px;
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 0.2px;
}
QPushButton#dockGhost {
  border-radius: 14px;
  padding: 12px 16px;
  font-size: 15px;
}

QCheckBox { spacing: 10px; font-size: 15px; font-weight: 600; }
QCheckBox::indicator {
  width: 20px;
  height: 20px;
  border-radius: 6px;
}

QProgressBar {
  border: 0;
  border-radius: 999px;
  height: 10px;
  text-align: center;
  color: transparent;
  max-height: 10px;
}
QProgressBar::chunk { border-radius: 999px; }

QTableWidget#analyticsTable {
  border-radius: 14px;
  gridline-color: rgba(127, 127, 127, 0.28);
  font-size: 15px;
  selection-background-color: transparent;
}
QTableWidget#analyticsTable::item {
  padding: 12px 10px;
}
QTableWidget#analyticsTable QPushButton#ghost {
  padding: 7px 12px;
  font-size: 14px;
  min-height: 0;
}
QHeaderView::section {
  padding: 12px 12px;
  font-size: 14px;
  font-weight: 800;
  border: 0;
  border-right: 1px solid rgba(127, 127, 127, 0.22);
}

QScrollArea, QScrollArea#listScroll {
  border: 0;
  background: transparent;
}
QAbstractScrollArea::viewport, QWidget#listViewport, QWidget#listHost {
  background: transparent;
  border: 0;
}
QScrollBar:vertical {
  background: transparent;
  width: 11px;
  margin: 4px 0;
}
QScrollBar::handle:vertical {
  border-radius: 5px;
  min-height: 32px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
  background: transparent;
  height: 11px;
  margin: 0 4px;
}
QScrollBar::handle:horizontal {
  border-radius: 5px;
  min-width: 32px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QComboBox#themePick {
  min-width: 108px;
  padding: 10px 12px;
}

QMessageBox {
  background: #f4faf6;
  color: #102820;
}
QMessageBox QLabel {
  color: #102820;
  min-width: 360px;
}
QMessageBox QPushButton {
  min-width: 72px;
  background: #1f7a55;
  color: #ffffff;
  border: 0;
  border-radius: 8px;
  padding: 8px 14px;
}
"""

LIGHT_STYLE = SHARED + """
QMainWindow, QWidget#central { color: #102820; }

QLabel#brand { color: #0c3326; }
QLabel#tagline { color: #355e4c; }
QLabel#sectionTitle { color: #0c3326; }
QLabel#sectionHint { color: #3f6a58; }
QLabel#meta { color: #ecf8f1; }
QLabel#metaSub { color: rgba(236, 248, 241, 0.75); }
QLabel#muted { color: #3f6a58; }
QLabel#state { color: #0c3326; }
QLabel#stateOk { color: #146c43; }
QLabel#stateBad { color: #9b2c2c; }
QLabel#stateRun { color: #0b5cab; }
QLabel#stateIdle { color: #4a6f5d; }
QLabel#jobLine { color: #2d5645; }
QLabel#jobLine a { color: #146c43; text-decoration: underline; }
QLabel#jobUrl { color: #3f6a58; }
QLabel#emptyTitle { color: #0c3326; }

QFrame#panel {
  background: #e4efe8;
  border: 1px solid #b7cfc0;
}
QFrame#row {
  background: #dce8e0;
  border: 1px solid #b7cfc0;
}
QFrame#statusCard {
  background: #f3faf5;
  border: 1px solid #b7cfc0;
}
QTableWidget#analyticsTable {
  background: #dce8e0;
  color: #102820;
  border: 1px solid #b7cfc0;
  alternate-background-color: #e4efe8;
}
QHeaderView::section {
  background: #cfe0d6;
  color: #0c3326;
}
QFrame#dock { background: #0f3d2e; }

QScrollArea#listScroll, QWidget#listViewport, QWidget#listHost {
  background: transparent;
}

QFrame#panel QLabel, QFrame#row QLabel, QFrame#statusCard QLabel {
  color: #102820;
}
QFrame#panel QLabel#sectionHint, QFrame#panel QLabel#muted,
QFrame#row QLabel#muted, QFrame#statusCard QLabel#muted {
  color: #3f6a58;
}
QFrame#statusCard QLabel#state { color: #0c3326; }
QFrame#statusCard QLabel#stateOk { color: #146c43; }
QFrame#statusCard QLabel#stateBad { color: #9b2c2c; }
QFrame#statusCard QLabel#stateRun { color: #0b5cab; }
QFrame#statusCard QLabel#stateIdle { color: #4a6f5d; }
QFrame#statusCard QLabel#jobLine { color: #2d5645; }
QFrame#statusCard QLabel#jobUrl { color: #3f6a58; }
QFrame#statusCard QLabel#sectionTitle { color: #0c3326; }

QLineEdit, QSpinBox, QComboBox {
  background: #ffffff;
  border: 1px solid #9fbfae;
  color: #102820;
  selection-background-color: #b7e0c8;
  selection-color: #0c3326;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
  border: 1px solid #1f7a55;
  background: #ffffff;
}

QPushButton {
  background: #dceadf;
  border: 1px solid #9fbfae;
  color: #0c3326;
}
QPushButton:hover { background: #cfe0d5; }
QPushButton#primary { background: #1f7a55; border: 0; color: #ffffff; }
QPushButton#primary:hover { background: #186746; }
QPushButton#ghost {
  background: #ffffff;
  border: 1px solid #9fbfae;
  color: #0c3326;
}
QPushButton#danger {
  background: #ffffff;
  border: 1px solid #d59a9a;
  color: #8f2f2f;
}
QPushButton#danger:hover { background: #fdecec; }
QPushButton#start { background: #d7ef7a; color: #143226; }
QPushButton#start:hover { background: #e5f79a; }
QPushButton#start[running="true"] { background: #ffb4a8; color: #5c1d14; }
QPushButton#dockGhost {
  background: rgba(255,255,255,0.10);
  border: 1px solid rgba(255,255,255,0.22);
  color: #ecf8f1;
}
QPushButton#dockGhost:hover { background: rgba(255,255,255,0.18); }

QComboBox#themePick {
  background: rgba(255,255,255,0.12);
  border: 1px solid rgba(255,255,255,0.24);
  color: #ecf8f1;
}
QComboBox#themePick QAbstractItemView {
  background: #0f3d2e;
  color: #ecf8f1;
  selection-background-color: #1f7a55;
}

QCheckBox, QFrame#panel QCheckBox, QFrame#row QCheckBox {
  color: #102820;
}
QCheckBox::indicator {
  border: 1.5px solid #5d8a74;
  background: #ffffff;
}
QCheckBox::indicator:checked {
  background: #1f7a55;
  border-color: #1f7a55;
}

QProgressBar { background: #d5e5db; }
QProgressBar::chunk {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f7a55, stop:1 #8fbf3f);
}
QScrollBar::handle:vertical { background: #9fbfae; }

QDialog { background: #eef5f0; color: #102820; }
QDialog QLabel { color: #102820; }
"""

DARK_STYLE = SHARED + """
QMainWindow, QWidget#central { color: #e8f2eb; }

QLabel#brand { color: #e8f7b5; }
QLabel#tagline { color: #a9c2b4; }
QLabel#sectionTitle { color: #eef7f1; }
QLabel#sectionHint { color: #9eb8a8; }
QLabel#meta { color: #ecf8f1; }
QLabel#metaSub { color: rgba(236, 248, 241, 0.70); }
QLabel#muted { color: #9eb8a8; }
QLabel#state { color: #e8f7b5; }
QLabel#stateOk { color: #b8e986; }
QLabel#stateBad { color: #ffb4a8; }
QLabel#stateRun { color: #9fd4ff; }
QLabel#stateIdle { color: #9eb8a8; }
QLabel#jobLine { color: #b7cfc2; }
QLabel#jobLine a { color: #e8f7b5; text-decoration: underline; }
QLabel#jobUrl { color: #9eb8a8; }
QLabel#emptyTitle { color: #eef7f1; }

QFrame#panel {
  background: #15221d;
  border: 1px solid #2f433a;
}
QFrame#row {
  background: #1a2a24;
  border: 1px solid #334840;
}
QFrame#statusCard {
  background: #1f322a;
  border: 1px solid #3a5247;
}
QTableWidget#analyticsTable {
  background: #1a2a24;
  color: #e8f2eb;
  border: 1px solid #334840;
  alternate-background-color: #17241f;
}
QHeaderView::section {
  background: #20332c;
  color: #eef7f1;
}
QFrame#dock { background: #0b1612; }

QScrollArea#listScroll, QWidget#listViewport, QWidget#listHost {
  background: transparent;
}

QFrame#panel QLabel, QFrame#row QLabel, QFrame#statusCard QLabel {
  color: #e8f2eb;
}
QFrame#panel QLabel#sectionHint, QFrame#panel QLabel#muted,
QFrame#row QLabel#muted, QFrame#statusCard QLabel#muted {
  color: #9eb8a8;
}
QFrame#statusCard QLabel#state { color: #e8f7b5; }
QFrame#statusCard QLabel#stateOk { color: #b8e986; }
QFrame#statusCard QLabel#stateBad { color: #ffb4a8; }
QFrame#statusCard QLabel#stateRun { color: #9fd4ff; }
QFrame#statusCard QLabel#stateIdle { color: #9eb8a8; }
QFrame#statusCard QLabel#jobLine { color: #b7cfc2; }
QFrame#statusCard QLabel#jobUrl { color: #9eb8a8; }
QFrame#statusCard QLabel#sectionTitle { color: #eef7f1; }

QLineEdit, QSpinBox, QComboBox {
  background: #101a16;
  border: 1px solid #4a6658;
  color: #e8f2eb;
  selection-background-color: #2f8f68;
  selection-color: #f4fff8;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
  border: 1px solid #8fbf3f;
  background: #14201b;
}

QPushButton {
  background: #24352e;
  border: 1px solid #4a6658;
  color: #e8f7b5;
}
QPushButton:hover { background: #2d4339; }
QPushButton#primary { background: #2f8f68; border: 0; color: #ffffff; }
QPushButton#primary:hover { background: #267554; }
QPushButton#ghost {
  background: #17241f;
  border: 1px solid #4a6658;
  color: #e8f7b5;
}
QPushButton#danger {
  background: #241818;
  border: 1px solid #8a4545;
  color: #fecaca;
}
QPushButton#danger:hover { background: #3a2020; }
QPushButton#start { background: #e8f7b5; color: #143226; }
QPushButton#start:hover { background: #f0ffc4; }
QPushButton#start[running="true"] { background: #ffb4a8; color: #5c1d14; }
QPushButton#dockGhost {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.16);
  color: #ecf8f1;
}
QPushButton#dockGhost:hover { background: rgba(255,255,255,0.14); }

QComboBox#themePick {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.16);
  color: #ecf8f1;
}
QComboBox#themePick QAbstractItemView {
  background: #17241f;
  color: #ecf8f1;
  selection-background-color: #2f8f68;
}

QCheckBox, QFrame#panel QCheckBox, QFrame#row QCheckBox {
  color: #e8f2eb;
}
QCheckBox::indicator {
  border: 1.5px solid #7aa190;
  background: #101a16;
}
QCheckBox::indicator:checked {
  background: #2f8f68;
  border-color: #2f8f68;
}

QProgressBar { background: #2a3b33; }
QProgressBar::chunk {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f8f68, stop:1 #e8f7b5);
}
QScrollBar::handle:vertical { background: #4a6658; }

QDialog { background: #17241f; color: #e8f2eb; }
QDialog QLabel { color: #e8f2eb; }

QMessageBox {
  background: #17241f;
  color: #e8f2eb;
}
QMessageBox QLabel { color: #e8f2eb; }
QMessageBox QPushButton {
  background: #2f8f68;
  color: #ffffff;
}
"""

LIGHT_BG = {
    "stops": [("#dceadf", 0.0), ("#eef5f0", 0.45), ("#d5e5db", 1.0)],
    "orbs": [
        {"rgba": (143, 191, 63, 45), "anchor": "tl", "size": (320, 260), "offset": (-80, -60)},
        {"rgba": (47, 143, 104, 35), "anchor": "br", "size": (340, 300), "offset": (-80, -20)},
        {"rgba": (255, 255, 255, 40), "anchor": "mid", "size": (220, 140), "offset": (0, 40)},
    ],
    "shadow": (15, 61, 46, 35),
}

DARK_BG = {
    "stops": [("#0b1411", 0.0), ("#121c18", 0.5), ("#0e1914", 1.0)],
    "orbs": [
        {"rgba": (47, 143, 104, 40), "anchor": "tl", "size": (340, 280), "offset": (-90, -70)},
        {"rgba": (232, 247, 181, 16), "anchor": "br", "size": (360, 320), "offset": (-90, -40)},
        {"rgba": (15, 61, 46, 70), "anchor": "mid", "size": (240, 160), "offset": (0, 30)},
    ],
    "shadow": (0, 0, 0, 80),
}


def normalize_theme(value: str | None) -> ThemeChoice:
    raw = (value or "system").strip().lower()
    if raw in {"light", "dark", "system"}:
        return raw  # type: ignore[return-value]
    return "system"


def system_prefers_dark() -> bool:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return int(value) == 0
        except OSError:
            return False

    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.check_output(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            return "dark" in out.lower()
        except Exception:
            return False

    return False


def resolve_theme(choice: str | None) -> ResolvedTheme:
    mode = normalize_theme(choice)
    if mode == "system":
        return "dark" if system_prefers_dark() else "light"
    return mode  # type: ignore[return-value]


def stylesheet_for(resolved: ResolvedTheme) -> str:
    return DARK_STYLE if resolved == "dark" else LIGHT_STYLE


def background_for(resolved: ResolvedTheme) -> dict:
    return DARK_BG if resolved == "dark" else LIGHT_BG
