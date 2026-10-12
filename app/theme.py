from __future__ import annotations

import sys
from typing import Literal

ThemeChoice = Literal["light", "dark", "system"]
ResolvedTheme = Literal["light", "dark"]

SHARED = """
* {
  font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
  font-size: 14px;
}

QMainWindow, QWidget#appRoot, QWidget#content {
  background: transparent;
}

QLabel#sideTitle {
  font-size: 13px;
  font-weight: 600;
  padding: 4px 10px 10px 10px;
}
QLabel#sectionTitle {
  font-size: 16px;
  font-weight: 650;
}
QLabel#sectionHint, QLabel#muted, QLabel#metaSub { font-size: 13px; }
QLabel#meta { font-size: 15px; font-weight: 650; }
QLabel#stateOk, QLabel#stateBad, QLabel#stateRun, QLabel#stateIdle {
  font-size: 13px;
  font-weight: 600;
}
QLabel#emptyTitle { font-size: 14px; font-weight: 650; }

QFrame#sidebar { border: 0; }
QFrame#panel, QFrame#resultCard {
  border-radius: 10px;
}
QFrame#row { border-radius: 8px; }

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
  border-radius: 8px;
  padding: 8px 10px;
  min-height: 20px;
  font-size: 14px;
}
QComboBox::drop-down { border: 0; width: 24px; }
QSpinBox::up-button, QSpinBox::down-button { width: 16px; }

QPushButton {
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 14px;
  font-weight: 600;
}
QPushButton#nav {
  text-align: left;
  border: 0;
  border-radius: 8px;
  padding: 8px 12px;
  font-weight: 500;
}
QPushButton#start {
  min-width: 88px;
  padding: 8px 16px;
  border: 0;
  border-radius: 8px;
  font-weight: 650;
}
QPushButton#danger {
  min-width: 32px;
  max-width: 36px;
  padding: 4px 0;
  font-size: 16px;
}

QCheckBox { spacing: 8px; font-size: 14px; }
QCheckBox::indicator {
  width: 16px;
  height: 16px;
  border-radius: 4px;
}

QProgressBar {
  border: 0;
  border-radius: 999px;
  max-height: 6px;
  text-align: center;
  color: transparent;
}
QProgressBar::chunk { border-radius: 999px; }

QTableWidget#progressTable {
  border-radius: 8px;
  font-size: 13px;
}
QTableWidget#progressTable::item { padding: 4px 8px; }
QHeaderView::section {
  padding: 6px 8px;
  font-size: 13px;
  font-weight: 600;
  border: 0;
  border-bottom: 1px solid transparent;
  border-right: 1px solid transparent;
}

QTabWidget::pane { border: 0; background: transparent; }
QTabBar::tab {
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  padding: 8px 14px;
  margin-right: 4px;
  font-weight: 600;
}
QTabBar::tab:selected { background: transparent; }

QScrollArea, QScrollArea#listScroll { border: 0; background: transparent; }
QAbstractScrollArea::viewport, QWidget#listViewport, QWidget#listHost {
  background: transparent;
  border: 0;
}
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px 0; }
QScrollBar::handle:vertical { border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0 2px; }
QScrollBar::handle:horizontal { border-radius: 4px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QMessageBox QLabel { min-width: 320px; }
QMessageBox QPushButton {
  min-width: 72px;
  border: 0;
  border-radius: 6px;
  padding: 6px 12px;
}
"""

LIGHT_STYLE = SHARED + """
QMainWindow, QWidget#appRoot, QWidget#content { background: #f4f5f7; color: #1f2937; }
QFrame#sidebar { background: #f7f8fa; border-right: 1px solid #e6e8ec; }
QLabel#sideTitle { color: #98a2b3; }
QLabel#sectionTitle, QLabel#emptyTitle, QLabel#meta { color: #111827; }
QLabel#sectionHint, QLabel#muted, QLabel#metaSub { color: #6b7280; }
QLabel#stateOk { color: #15803d; }
QLabel#stateBad { color: #b91c1c; }
QLabel#stateRun { color: #1d4ed8; }
QLabel#stateIdle { color: #6b7280; }

QFrame#panel, QFrame#resultCard {
  background: #ffffff;
  border: 1px solid #e6e8ec;
}
QFrame#row { background: #f8fafc; border: 1px solid #e6e8ec; }

QFrame#panel QLabel, QFrame#row QLabel, QFrame#resultCard QLabel { color: #1f2937; }
QFrame#panel QLabel#sectionHint, QFrame#panel QLabel#muted,
QFrame#row QLabel#muted, QFrame#resultCard QLabel#muted { color: #6b7280; }
QFrame#resultCard QLabel#stateOk { color: #15803d; }
QFrame#resultCard QLabel#stateBad { color: #b91c1c; }
QFrame#resultCard QLabel#stateRun { color: #1d4ed8; }
QFrame#resultCard QLabel#stateIdle { color: #6b7280; }

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
  background: #ffffff;
  border: 1px solid #d0d5dd;
  color: #111827;
  selection-background-color: #dbeafe;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
  border: 1px solid #2563eb;
}

QPushButton {
  background: #ffffff;
  border: 1px solid #d0d5dd;
  color: #1f2937;
}
QPushButton:hover { background: #f3f4f6; }
QPushButton#primary, QPushButton#start {
  background: #2563eb;
  border: 0;
  color: #ffffff;
}
QPushButton#primary:hover, QPushButton#start:hover { background: #1d4ed8; }
QPushButton#start[running="true"] {
  background: #fee2e2;
  border: 1px solid #fecaca;
  color: #991b1b;
}
QPushButton#ghost {
  background: #ffffff;
  border: 1px solid #d0d5dd;
  color: #1f2937;
}
QPushButton#danger {
  background: #ffffff;
  border: 1px solid #fecaca;
  color: #b91c1c;
}
QPushButton#nav {
  background: transparent;
  color: #374151;
}
QPushButton#nav:hover { background: #eef2f6; }
QPushButton#nav[active="true"] {
  background: #e8f1fe;
  color: #1d4ed8;
}
QPushButton#icon {
  background: #ffffff;
  border: 1px solid #d0d5dd;
  padding: 4px;
}
QPushButton#icon[active="true"] {
  background: #dbeafe;
  border: 1px solid #2563eb;
}

QCheckBox, QFrame#panel QCheckBox, QFrame#row QCheckBox { color: #1f2937; background: transparent; }
QCheckBox::indicator { border: 1px solid #98a2b3; background: #ffffff; }
QCheckBox::indicator:checked { background: #ffffff; border-color: #2563eb; }
QComboBox QAbstractItemView {
  background: #ffffff;
  color: #111827;
  selection-background-color: #2563eb;
  selection-color: #ffffff;
  border: 1px solid #d0d5dd;
}

QTabBar::tab { color: #6b7280; }
QTabBar::tab:selected { color: #1d4ed8; border-bottom: 2px solid #2563eb; }

QProgressBar { background: #e5e7eb; }
QProgressBar::chunk { background: #2563eb; }
QTableWidget#progressTable {
  background: #ffffff;
  color: #1f2937;
  alternate-background-color: #f8fafc;
  border: 1px solid #e6e8ec;
  gridline-color: #e6e8ec;
}
QHeaderView::section {
  background: #f8fafc;
  color: #374151;
  border-bottom: 1px solid #e6e8ec;
  border-right: 1px solid #e6e8ec;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #d0d5dd; }

QDialog { background: #ffffff; color: #1f2937; }
QMessageBox { background: #ffffff; color: #1f2937; }
QMessageBox QLabel { color: #1f2937; }
QMessageBox QPushButton { background: #2563eb; color: #ffffff; }
"""

DARK_STYLE = SHARED + """
QMainWindow, QWidget#appRoot, QWidget#content { background: #1c1c1e; color: #f3f4f6; }
QFrame#sidebar { background: #161618; border-right: 1px solid #2c2c2e; }
QLabel#sideTitle { color: #9ca3af; }
QLabel#sectionTitle, QLabel#emptyTitle, QLabel#meta { color: #f9fafb; }
QLabel#sectionHint, QLabel#muted, QLabel#metaSub { color: #9ca3af; }
QLabel#stateOk { color: #86efac; }
QLabel#stateBad { color: #fca5a5; }
QLabel#stateRun { color: #93c5fd; }
QLabel#stateIdle { color: #9ca3af; }

QFrame#panel, QFrame#resultCard {
  background: #2c2c2e;
  border: 1px solid #3a3a3c;
}
QFrame#row { background: #1c1c1e; border: 1px solid #3a3a3c; }

QFrame#panel QLabel, QFrame#row QLabel, QFrame#resultCard QLabel { color: #f3f4f6; }
QFrame#panel QLabel#sectionHint, QFrame#panel QLabel#muted,
QFrame#row QLabel#muted, QFrame#resultCard QLabel#muted { color: #9ca3af; }
QFrame#resultCard QLabel#stateOk { color: #86efac; }
QFrame#resultCard QLabel#stateBad { color: #fca5a5; }
QFrame#resultCard QLabel#stateRun { color: #93c5fd; }
QFrame#resultCard QLabel#stateIdle { color: #9ca3af; }

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
  background: #1c1c1e;
  border: 1px solid #3a3a3c;
  color: #f9fafb;
  selection-background-color: #1d4ed8;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
  border: 1px solid #3b82f6;
}

QPushButton {
  background: #2c2c2e;
  border: 1px solid #3a3a3c;
  color: #f3f4f6;
}
QPushButton:hover { background: #3a3a3c; }
QPushButton#primary, QPushButton#start {
  background: #2563eb;
  border: 0;
  color: #ffffff;
}
QPushButton#primary:hover, QPushButton#start:hover { background: #1d4ed8; }
QPushButton#start[running="true"] {
  background: #3f1d1d;
  border: 1px solid #7f1d1d;
  color: #fecaca;
}
QPushButton#ghost {
  background: #2c2c2e;
  border: 1px solid #3a3a3c;
  color: #f3f4f6;
}
QPushButton#danger {
  background: #2c2c2e;
  border: 1px solid #7f1d1d;
  color: #fca5a5;
}
QPushButton#nav {
  background: transparent;
  color: #e5e7eb;
}
QPushButton#nav:hover { background: #2c2c2e; }
QPushButton#nav[active="true"] {
  background: #1e3a5f;
  color: #bfdbfe;
}
QPushButton#icon {
  background: #2c2c2e;
  border: 1px solid #3a3a3c;
  padding: 4px;
}
QPushButton#icon[active="true"] {
  background: #1e3a5f;
  border: 1px solid #60a5fa;
}

QLabel { color: #f3f4f6; }
QCheckBox, QFrame#panel QCheckBox, QFrame#row QCheckBox { color: #f3f4f6; background: transparent; }
QCheckBox::indicator { border: 1px solid #6b7280; background: #1c1c1e; }
QCheckBox::indicator:checked { background: #1c1c1e; border-color: #60a5fa; }
QComboBox QAbstractItemView {
  background: #1c1c1e;
  color: #f9fafb;
  selection-background-color: #2563eb;
  selection-color: #ffffff;
  border: 1px solid #3a3a3c;
}

QTabBar::tab { color: #9ca3af; }
QTabBar::tab:selected { color: #93c5fd; border-bottom: 2px solid #3b82f6; }

QProgressBar { background: #3a3a3c; }
QProgressBar::chunk { background: #3b82f6; }
QTableWidget#progressTable {
  background: #1c1c1e;
  color: #f3f4f6;
  alternate-background-color: #2c2c2e;
  border: 1px solid #3a3a3c;
  gridline-color: #3a3a3c;
}
QHeaderView::section {
  background: #2c2c2e;
  color: #e5e7eb;
  border-bottom: 1px solid #3a3a3c;
  border-right: 1px solid #3a3a3c;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #4b5563; }

QDialog { background: #2c2c2e; color: #f3f4f6; }
QDialog QLabel { color: #f3f4f6; }
QMessageBox { background: #2c2c2e; color: #f3f4f6; }
QMessageBox QLabel { color: #f3f4f6; }
QMessageBox QPushButton { background: #2563eb; color: #ffffff; }
"""


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
