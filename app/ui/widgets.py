from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor, QPainter, QPen, QPalette
from PyQt5.QtWidgets import (
    QCheckBox,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class TickCheckBox(QCheckBox):
    """Checked state is a tick inside the box, not a filled square."""

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = 16
        box = QRect(0, (self.height() - side) // 2, side, side)
        dark = _widget_is_dark(self)
        fill = QColor("#1c1c1e" if dark else "#ffffff")
        border = QColor("#60a5fa" if self.isChecked() and dark else "#2563eb" if self.isChecked() else ("#9ca3af" if dark else "#98a2b3"))
        painter.setPen(QPen(border, 1.4))
        painter.setBrush(fill)
        painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), 3, 3)

        if self.isChecked():
            painter.setPen(QPen(QColor("#93c5fd" if dark else "#2563eb"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(box.left() + 4, box.center().y(), box.left() + 7, box.bottom() - 4)
            painter.drawLine(box.left() + 7, box.bottom() - 4, box.right() - 3, box.top() + 4)

        text_rect = self.rect().adjusted(side + 8, 0, 0, 0)
        text = QColor("#f3f4f6" if dark else "#111827")
        painter.setPen(text)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(max(hint.height(), 24))
        return hint


def _widget_is_dark(widget: QWidget) -> bool:
    """Follow the app theme, including dialogs opened from the main window."""
    current: QWidget | None = widget
    while current is not None:
        theme = getattr(current, "_resolved_theme", None)
        if theme == "dark":
            return True
        if theme == "light":
            return False
        parent = current.parentWidget()
        if parent is None:
            break
        current = parent
    return widget.palette().color(QPalette.Window).lightness() < 140


def polish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def section(_host: Any, title: str, hint: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    sub = QLabel(hint)
    sub.setObjectName("sectionHint")
    sub.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(sub)
    return frame


def scroll_area(inner_layout: QVBoxLayout) -> QScrollArea:
    host = QWidget()
    host.setObjectName("listHost")
    host.setAttribute(Qt.WA_StyledBackground, True)
    host.setLayout(inner_layout)
    inner_layout.setContentsMargins(0, 0, 0, 0)
    inner_layout.setSpacing(8)
    scroll = QScrollArea()
    scroll.setObjectName("listScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setAttribute(Qt.WA_StyledBackground, True)
    if scroll.viewport():
        scroll.viewport().setObjectName("listViewport")
        scroll.viewport().setAttribute(Qt.WA_StyledBackground, True)
    scroll.setWidget(host)
    return scroll


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        child = item.layout()
        if child is not None:
            clear_layout(child)


def empty_state(title: str, body: str) -> QFrame:
    box = QFrame()
    box.setObjectName("row")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(16, 18, 16, 18)
    heading = QLabel(title)
    heading.setObjectName("emptyTitle")
    text = QLabel(body)
    text.setObjectName("muted")
    text.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(text)
    return box
